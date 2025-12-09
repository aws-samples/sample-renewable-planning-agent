import json
import requests
import os
import numpy as np
import pandas as pd
from io import StringIO
from scipy import stats
from typing import Dict, Optional
import random
import logging

# Configure logging
log_level = logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)
logger = logging.getLogger('get_wind_conditions')


def fetch_wind_data(latitude, longitude, year=2023):
    """Fetch wind data from NREL API"""
    api_base_url = os.getenv('NREL_API_BASE_URL')
    api_key = os.getenv('NREL_API_KEY', 'DEMO_KEY')
    api_email = os.getenv('NREL_API_EMAIL')

    url = (f'{api_base_url}?'
           f'api_key={api_key}&'
           f'wkt=POINT({longitude} {latitude})&'
           f'attributes=windspeed_100m,winddirection_100m&'
           f'years={year}&'
           f'email={api_email}')

    headers = {
        'content-type': "application/x-www-form-urlencoded",
        'cache-control': "no-cache"
    }

    response = requests.post(url, headers=headers, timeout=60)

    if response.status_code == 200:
        return response.text
    else:
        raise Exception(
            f"Unable to fetch wind data (Status: {response.status_code})")


def process_wind_data(wind_data_csv):
    """Process raw CSV wind data from NREL API into wind conditions for PyWake"""
    # Parse CSV using pandas
    df = pd.read_csv(StringIO(wind_data_csv), skiprows=1)

    # Extract wind speed and direction data
    wind_speeds = pd.to_numeric(
        df.iloc[:, 5], errors='coerce').values  # Wind Speed at 100m
    wind_directions = pd.to_numeric(
        df.iloc[:, 6], errors='coerce').values  # Wind Direction at 100m

    # Filter out invalid data
    valid_mask = (wind_speeds > 0) & (
        ~np.isnan(wind_speeds)) & (~np.isnan(wind_directions))
    wind_speeds = wind_speeds[valid_mask]
    wind_directions = wind_directions[valid_mask]

    # Calculate wind direction sectors (12 sectors of 30 degrees)
    wd_bins = np.arange(0, 361, 30)
    n_sectors = len(wd_bins) - 1

    # Calculate frequency distribution for each sector
    p_wd = np.zeros(n_sectors)
    a_weibull = np.zeros(n_sectors)  # Weibull scale parameter
    k_weibull = np.zeros(n_sectors)  # Weibull shape parameter

    for i in range(n_sectors):
        # Find wind speeds in this direction sector
        mask = ((wind_directions >= wd_bins[i]) & (
            wind_directions < wd_bins[i+1]))
        sector_speeds = wind_speeds[mask]

        if len(sector_speeds) > 10:  # Need sufficient data for Weibull fit
            p_wd[i] = len(sector_speeds) / len(wind_speeds)

            # Fit Weibull distribution to sector wind speeds
            try:
                k, loc, a = stats.weibull_min.fit(sector_speeds, floc=0)
                k_weibull[i] = k
                a_weibull[i] = a
            except:
                # Fallback to overall statistics if fit fails
                k_weibull[i] = 2.0
                a_weibull[i] = np.mean(sector_speeds)
        else:
            # Use overall statistics for sectors with little data
            p_wd[i] = 1.0 / n_sectors  # Equal probability
            k_weibull[i] = 2.0
            a_weibull[i] = np.mean(wind_speeds)

    # Normalize probabilities
    p_wd = p_wd / np.sum(p_wd)

    # Calculate prevailing wind direction (sector with highest probability)
    prevailing_sector_idx = np.argmax(p_wd)
    prevailing_wind_direction = int(wd_bins[prevailing_sector_idx])

    return {
        'p_wd': p_wd.tolist(),
        'a': a_weibull.tolist(),
        'k': k_weibull.tolist(),
        'wd_bins': wd_bins[:-1].tolist(),
        'ti': 0.1,  # Turbulence intensity
        'mean_wind_speed': float(np.mean(wind_speeds)),
        'total_hours': len(wind_speeds),
        'prevailing_wind_direction': prevailing_wind_direction
    }


def get_wind_conditions(latitude: float, longitude: float, year: int = 2023) -> Dict:
    """
    Fetch wind data from NREL API for a specific location and year

    Args:
        latitude: Latitude coordinate of the location
        longitude: Longitude coordinate of the location  
        year: Year for wind data (default: 2023)

    Returns:
        Dict with the wind conditions for the location
    """
    logger.info(
        f"Fetching wind data for lat={latitude}, lon={longitude}, year={year}")

    try:
        wind_data = fetch_wind_data(latitude, longitude, year)
        wind_conditions = process_wind_data(wind_data)
        logger.debug("Wind data fetched and processed successfully")
        return wind_conditions
    except Exception as e:
        logger.error(f"Error fetching wind data: {e}")
        return f"Error fetching wind data: {str(e)}"
