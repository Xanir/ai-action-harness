@echo Delete and Restart PM2 MCP wrappers
call pm2 delete ./mcp_sse_wrappers/mcp_wrappers.config.json 2>nul

call pm2 start ./mcp_sse_wrappers/mcp_wrappers.config.json

@echo Stop the Docker container
call docker compose -f docker/compose.yml down 2>nul

@echo Remove the Docker image
call docker compose -f docker/compose.yml rm -f 2>nul

@echo Build the Docker image
call docker compose -f docker/compose.yml build

@echo Run the Docker Image
call docker compose -f docker/compose.yml up -d
