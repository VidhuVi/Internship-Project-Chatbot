import azure.functions as func
import logging
import json
import os
import http.client # For standard HTTP status codes

from fastapi_app import app as fastapi_app # Correctly import your FastAPI app instance

logging.basicConfig(level=logging.INFO) # Ensure logging is configured here too


# --- Azure Function App wrapper for FastAPI ---
az_func_app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# This route configuration means ALL requests to "/api/*" will be routed to this function
# and then passed to the FastAPI app.
@az_func_app.route(route="{*route}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def HttpExample(req: func.HttpRequest) -> func.HttpResponse:
    logging.info(f"Azure Function HttpExample (wrapper) received request for path: {req.url}")
    try:
        # Handle OPTIONS requests for CORS preflight
        # FastAPI's CORSMiddleware typically handles this, but it's safer to have it here
        # at the Azure Function wrapper level too as a fallback/primary handler.
        if req.method == "OPTIONS":
            logging.info(f"Handling OPTIONS request for {req.url}")
            return func.HttpResponse(
                "", # Empty body for OPTIONS response
                status_code=http.client.OK, # 200 OK
                headers={
                    "Access-Control-Allow-Origin": "http://localhost:3000", # Allow your frontend origin
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS", # Allow all methods your API uses
                    "Access-Control-Allow-Headers": "Content-Type, X-Requested-With", # Allow common headers
                    "Access-Control-Max-Age": "86400" # Cache preflight response for 24 hours
                }
            )

        # Pass the request to the FastAPI application using AsgiMiddleware
        fastapi_response = await func.AsgiMiddleware(fastapi_app).handle_async(req)
        logging.info(f"FastAPI handled request, status: {fastapi_response.status_code}")
        return fastapi_response
    except Exception as e:
        logging.error(f"Error handling request with FastAPI AsgiMiddleware: {e}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"message": f"Internal server error in Azure Function wrapper: {str(e)}"}),
            mimetype="application/json",
            status_code=http.client.INTERNAL_SERVER_ERROR
        )