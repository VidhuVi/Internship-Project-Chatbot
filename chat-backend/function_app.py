import azure.functions as func
import logging
import json
import http.client
from fastapi_app import app as fastapi_app
logging.basicConfig(level=logging.INFO)
# --- Azure Function App wrapper for FastAPI ---
az_func_app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
#Request --> this function --> FastAPI app
@az_func_app.route(route="{*route}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def HttpExample(req: func.HttpRequest) -> func.HttpResponse:
    logging.info(f"Azure Function HttpExample (wrapper) received request for path: {req.url}")
    try:
        if req.method == "OPTIONS":
            logging.info(f"Handling OPTIONS request for {req.url}")
            return func.HttpResponse(
                "",
                status_code=http.client.OK,
                headers={
                    "Access-Control-Allow-Origin": "http://localhost:3000", 
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, X-Requested-With",
                    "Access-Control-Max-Age": "86400"
                }
            )
        #Request passed to FastAPI app
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