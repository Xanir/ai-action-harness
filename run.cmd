@echo Delete and Restart PM2 MCP wrappers
call pm2 delete ./mcp_sse_wrappers/mcp_wrappers.config.json 2>nul

call pm2 start ./mcp_sse_wrappers/mcp_wrappers.config.json

@echo Stop the Docker container
call docker stop ai-action-harness 2>nul

@echo Stop the Docker image
call docker rm ai-action-harness 2>nul

@echo Build the Docker image
call docker build -t ai-action-harness .

@echo Run the Docker Image
call docker run --name ai-action-harness --add-host host.docker.internal:host-gateway ai-action-harness
