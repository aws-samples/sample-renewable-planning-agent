import { useEffect, useRef, useState } from "react";
import "ol/ol.css";
import { Map as OLMap, View } from "ol";
import TileLayer from "ol/layer/Tile";
import OSM from "ol/source/OSM";
import XYZ from "ol/source/XYZ";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import GeoJSON from "ol/format/GeoJSON";
import { fromLonLat, toLonLat } from "ol/proj";
import { Point } from "ol/geom";
import { Feature } from "ol";
import { Style, Circle, Fill, Stroke } from "ol/style";
import Overlay from "ol/Overlay";

interface MapProps {
  geojson?: any;
  geojsonLayers?: Array<{ filename: string; geojson: any }>;
  selectedCenterpoint?: { lat: number; lon: number } | null;
  onLocationClick?: (lat: number, lon: number) => void;
}

const Map = ({
  geojson,
  geojsonLayers,
  selectedCenterpoint,
  onLocationClick,
}: MapProps) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<OLMap | null>(null);
  const vectorLayer = useRef<VectorLayer<VectorSource> | null>(null);
  const markerLayer = useRef<VectorLayer<VectorSource> | null>(null);
  const hasZoomed = useRef(false);
  const [isSatellite, setIsSatellite] = useState(false);
  const [tooltip, setTooltip] = useState<{ content: string } | null>(null);
  const baseLayer = useRef<TileLayer<OSM | XYZ> | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<Overlay | null>(null);

  useEffect(() => {
    if (!mapContainer.current || map.current) return;

    vectorLayer.current = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => {
        const geometry = feature.getGeometry();
        const geometryType = geometry?.getType();
        const properties = feature.getProperties();
        const featureType =
          properties?.feature_type || properties?.type || "other";

        // Style for turbines (points) - use pins
        if (geometryType === "Point") {
          // Different colors for different point types
          const pointStyles: Record<string, { color: string; size: number }> = {
            turbine: { color: "#ff4444", size: 8 },
            substation: { color: "#ffa500", size: 6 },
            met_mast: { color: "#00ff00", size: 5 },
            other: { color: "#ff4444", size: 6 },
          };

          const style = pointStyles[featureType] || pointStyles.other;

          return new Style({
            image: new Circle({
              radius: style.size,
              fill: new Fill({ color: style.color }),
              stroke: new Stroke({ color: "#ffffff", width: 2 }),
            }),
          });
        }

        // Style for different polygon/line features
        const featureStyles: Record<
          string,
          { fillColor: string; strokeColor: string }
        > = {
          water: {
            fillColor: "rgba(59, 130, 246, 0.6)",
            strokeColor: "#1e40af",
          },
          roads: {
            fillColor: "rgba(245, 158, 11, 0.6)",
            strokeColor: "#d97706",
          },
          buildings: {
            fillColor: "rgba(239, 68, 68, 0.6)",
            strokeColor: "#dc2626",
          },
          boundary: {
            fillColor: "rgba(0, 102, 204, 0.3)",
            strokeColor: "#0066cc",
          },
          exclusion: {
            fillColor: "rgba(239, 68, 68, 0.3)",
            strokeColor: "#dc2626",
          },
          suitable: {
            fillColor: "rgba(34, 197, 94, 0.3)",
            strokeColor: "#16a34a",
          },
          other: {
            fillColor: "rgba(139, 92, 246, 0.6)",
            strokeColor: "#7c3aed",
          },
        };

        const style = featureStyles[featureType] || featureStyles.other;

        return new Style({
          fill: new Fill({ color: style.fillColor }),
          stroke: new Stroke({ color: style.strokeColor, width: 2 }),
        });
      },
    });

    markerLayer.current = new VectorLayer({
      source: new VectorSource(),
      style: new Style({
        image: new Circle({
          radius: 10,
          fill: new Fill({ color: "#ff00ff" }),
          stroke: new Stroke({ color: "#ffffff", width: 3 }),
        }),
      }),
    });

    baseLayer.current = new TileLayer({
      source: new OSM(),
    });

    map.current = new OLMap({
      target: mapContainer.current,
      layers: [baseLayer.current, vectorLayer.current, markerLayer.current],
      view: new View({
        center: fromLonLat([-98.5795, 39.8283]),
        zoom: 4,
      }),
    });

    // Create tooltip overlay
    if (tooltipRef.current) {
      overlayRef.current = new Overlay({
        element: tooltipRef.current,
        offset: [10, 0],
        positioning: "bottom-left",
      });
      map.current.addOverlay(overlayRef.current);
    }

    map.current.on("click", (event) => {
      const coords = toLonLat(event.coordinate);
      const [lon, lat] = coords;

      // Add marker at clicked location
      if (markerLayer.current) {
        const marker = new Feature({
          geometry: new Point(fromLonLat([lon, lat])),
        });
        markerLayer.current.getSource()?.clear();
        markerLayer.current.getSource()?.addFeature(marker);
      }

      // Zoom to clicked location (zoom level ~13 shows roughly 10km)
      map.current?.getView().animate({
        center: fromLonLat([lon, lat]),
        zoom: 13,
        duration: 500,
      });

      if (onLocationClick) {
        onLocationClick(lat, lon);
      }
    });

    // Add hover functionality
    map.current.on("pointermove", (event) => {
      const feature = map.current?.forEachFeatureAtPixel(
        event.pixel,
        (feature) => feature
      );

      if (
        feature &&
        feature instanceof Feature &&
        vectorLayer.current?.getSource()?.hasFeature(feature)
      ) {
        const properties = feature.getProperties();
        const featureType =
          properties?.feature_type || properties?.type || "Unknown";
        const geometry = feature.getGeometry();
        const geometryType = geometry?.getType();

        let content = `<strong>Type:</strong> ${featureType}<br/>`;
        content += `<strong>Geometry:</strong> ${geometryType}<br/>`;

        // Add specific properties based on feature type
        if (featureType === "turbine") {
          content += `<strong>ID:</strong> ${
            properties?.id || properties?.turbine_id || "N/A"
          }<br/>`;
          content += `<strong>Capacity:</strong> ${
            properties?.capacity || "N/A"
          } MW`;
        } else if (properties?.area) {
          content += `<strong>Area:</strong> ${properties.area} sq km`;
        } else if (properties?.name) {
          content += `<strong>Name:</strong> ${properties.name}`;
        }

        if (overlayRef.current) {
          overlayRef.current.setPosition(event.coordinate);
          setTooltip({ content });
        }
      } else {
        if (overlayRef.current) {
          overlayRef.current.setPosition(undefined);
        }
        setTooltip(null);
      }
    });
  }, [onLocationClick]);

  useEffect(() => {
    if (!vectorLayer.current || !geojson) return;

    const features = new GeoJSON().readFeatures(geojson, {
      featureProjection: "EPSG:3857",
    });

    vectorLayer.current.getSource()?.clear();
    vectorLayer.current.getSource()?.addFeatures(features);
  }, [geojson]);

  useEffect(() => {
    if (!vectorLayer.current) return;

    // Clear the layer first
    vectorLayer.current.getSource()?.clear();

    // If no layers, just return (map is now cleared)
    if (!geojsonLayers || geojsonLayers.length === 0) {
      console.log("Map: Clearing all features - no geojsonLayers");
      hasZoomed.current = false; // Reset zoom state for next project
      return;
    }

    console.log("Map: Loading", geojsonLayers.length, "GeoJSON layers");

    // Merge all GeoJSON layers
    const allFeatures: Feature[] = [];
    geojsonLayers.forEach((layer) => {
      const features = new GeoJSON().readFeatures(layer.geojson, {
        featureProjection: "EPSG:3857",
      }) as Feature[];

      // Determine agent type from filename for better styling
      const filename = layer.filename.toLowerCase();
      let agentType = "other";
      if (filename.includes("terrain")) agentType = "terrain";
      else if (filename.includes("layout") || filename.includes("turbine"))
        agentType = "layout";
      else if (filename.includes("boundary")) agentType = "boundary";

      features.forEach((feature, i) => {
        // Add agent type to feature properties for styling
        feature.set("agent_type", agentType);

        // If it's a point from layout agent, mark as turbine
        if (
          agentType === "layout" &&
          feature.getGeometry()?.getType() === "Point"
        ) {
          feature.set("feature_type", "turbine");
          feature.set("id", `turbine_${i}`);
          feature.set("capacity", "3.0"); // Default capacity
        }
      });

      allFeatures.push(...features);
    });

    // Add all features to the cleared layer
    vectorLayer.current.getSource()?.addFeatures(allFeatures);
    console.log("Map: Added", allFeatures.length, "features to map");

    // Zoom to fit all features (only on first load)
    if (allFeatures.length > 0 && map.current && !hasZoomed.current) {
      const extent = vectorLayer.current.getSource()?.getExtent();
      if (extent) {
        map.current
          .getView()
          .fit(extent, { padding: [50, 50, 50, 50], duration: 500 });
        hasZoomed.current = true;
      }
    }
  }, [geojsonLayers]);

  useEffect(() => {
    if (!markerLayer.current || !selectedCenterpoint) return;

    const marker = new Feature({
      geometry: new Point(
        fromLonLat([selectedCenterpoint.lon, selectedCenterpoint.lat])
      ),
    });
    markerLayer.current.getSource()?.clear();
    markerLayer.current.getSource()?.addFeature(marker);
  }, [selectedCenterpoint]);

  useEffect(() => {
    if (!baseLayer.current) return;

    if (isSatellite) {
      baseLayer.current.setSource(
        new XYZ({
          url: "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryTopo/MapServer/tile/{z}/{y}/{x}",
          maxZoom: 16,
        })
      );
    } else {
      baseLayer.current.setSource(new OSM());
    }
  }, [isSatellite]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      {/* Controls */}
      <div
        style={{
          position: "absolute",
          top: "16px",
          right: "16px",
          zIndex: 1000,
          display: "flex",
          flexDirection: "column",
          gap: "8px",
        }}
      >
        <button
          onClick={() => setIsSatellite(!isSatellite)}
          style={{
            padding: "8px 12px",
            background: "rgba(255, 255, 255, 0.9)",
            border: "none",
            borderRadius: "8px",
            fontSize: "12px",
            cursor: "pointer",
            backdropFilter: "blur(10px)",
            boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
            fontWeight: "500",
          }}
        >
          {isSatellite ? "Map View" : "USGS Imagery"}
        </button>
      </div>

      {/* Tooltip */}
      <div
        ref={tooltipRef}
        style={{
          background: "rgba(0, 0, 0, 0.8)",
          color: "white",
          padding: "8px 12px",
          borderRadius: "6px",
          fontSize: "12px",
          pointerEvents: "none",
          maxWidth: "200px",
          display: tooltip ? "block" : "none",
        }}
      >
        {tooltip?.content || ""}
      </div>

      <div ref={mapContainer} style={{ width: "100%", height: "100%" }} />
    </div>
  );
};

export default Map;
