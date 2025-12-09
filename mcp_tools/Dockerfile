FROM public.ecr.aws/lambda/python:3.12

# Copy requirements and install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install -r requirements.txt

RUN useradd -m -u 1000 runner
USER runner
HEALTHCHECK CMD netstat -an | grep "8080"

# Copy function code
COPY wind_tools_lambda.py get_wind_conditions.py __init__.py ${LAMBDA_TASK_ROOT}

CMD ["wind_tools_lambda.lambda_handler"]