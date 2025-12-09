include .makerc

archive: 
	git archive --format zip --output renewable-planning-assistant.zip main

push-images:
	aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com
	
	docker pull $(AGENT_IMAGE) --platform linux/arm64
	docker tag $(AGENT_IMAGE) $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/wind-dev-agent:latest
	aws ecr create-repository --repository-name wind-dev-agent --region $(AWS_REGION) || true
	docker push $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/wind-dev-agent:latest
	
	docker pull $(TOOL_IMAGE) --platform linux/arm64
	docker tag $(TOOL_IMAGE) $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/wind-tools-lambda-image:latest
	aws ecr create-repository --repository-name wind-tools-lambda-image --region $(AWS_REGION) || true
	docker push $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/wind-tools-lambda-image:latest

	docker pull $(APP_IMAGE) --platform linux/amd64
	docker tag $(APP_IMAGE) $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/wind-farm-app:latest
	aws ecr create-repository --repository-name wind-farm-app --region $(AWS_REGION) || true
	docker push $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/wind-farm-app:latest

build:
	sam validate --lint --region $(AWS_REGION)
	sam build --cached

deploy:
	sam deploy --parameter-overrides \
		ParameterKey=AgentImageUri,ParameterValue="$(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/wind-dev-agent:latest" \
		ParameterKey=ToolImageUri,ParameterValue="$(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/wind-tools-lambda-image:latest" \
		ParameterKey=AppImageUri,ParameterValue="$(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/wind-farm-app:latest" \
		ParameterKey=OverpassApiUrl,ParameterValue=$(OVERPASS_API_URL) \
		ParameterKey=NrelApiBaseUri,ParameterValue=$(NREL_API_BASE_URL) \
		ParameterKey=NrelApiKey,ParameterValue=$(NREL_API_KEY) \
		ParameterKey=NrelApiEmail,ParameterValue=$(NREL_API_EMAIL) \
		--no-confirm-changeset \
		--no-fail-on-empty-changeset \
		--capabilities CAPABILITY_IAM


delete:
	sam delete 

check:
	aws cloudformation describe-stack-events --stack-name wind-dev-agent --max-items 10
