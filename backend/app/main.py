from fastapi import FastAPI, HTTPException, Depends, WebSocket
from pydantic import BaseModel
from typing import List, Dict, Optional
import base64
from app.auth.jwt_handler import get_current_user
from app.services.ai_service import generate_product_description, generate_tags, categorize_ewaste_image, decide_recycle_or_resell, give_ques, websocket_endpoint


import json
import time
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException, Depends, WebSocket
from pydantic import BaseModel
from typing import List, Dict, Optional
from app.auth.jwt_handler import get_current_user
from app.services.ai_service import (
    generate_product_description, generate_tags, categorize_ewaste_image, 
    decide_recycle_or_resell, give_ques, websocket_endpoint
)

from datetime import datetime, timezone, timedelta
import json
import time
from fastapi import FastAPI, Request

LOG_FILE = "logs.json"


app = FastAPI()
IST = timezone(timedelta(hours=5, minutes=30))  # Define IST timezone


def log_request(request_data: dict):
    """Logs request and response details."""
    try:
        with open(LOG_FILE, "a") as log_file:
            log_file.write(json.dumps(request_data) + "\n")
    except Exception as e:
        print("Logging failed:", e)

@app.middleware("http")
async def log_middleware(request: Request, call_next):
    """Middleware to log all request details."""
    start_time = time.time()
    request_body = await request.body()
    headers = dict(request.headers)

    # Call the next middleware/handler
    response = await call_next(request)
    end_time = time.time()

    log_entry = {
        "timestamp": datetime.now(IST).isoformat(),  # Use IST time
        "method": request.method,
        "path": request.url.path,
        "query_params": dict(request.query_params),
        "headers": headers,  # Log all headers, including Auth token
        "request_body": request_body.decode("utf-8") if request_body else None,
        "status_code": response.status_code,
        "response_time": round(end_time - start_time, 4)
    }

    log_request(log_entry)
    return response


@app.get("/logs/")
async def get_logs(start_time: str, end_time: str):
    """
    Retrieve logs within a specific time range.
    - **start_time**: Start timestamp in ISO format (e.g., "2025-03-30T12:00:00").
    - **end_time**: End timestamp in ISO format (e.g., "2025-03-30T14:00:00").
    """
    try:
        start = datetime.fromisoformat(start_time).replace(tzinfo=IST)
        end = datetime.fromisoformat(end_time).replace(tzinfo=IST)
        logs = []

        with open(LOG_FILE, "r") as log_file:
            for line in log_file:
                entry = json.loads(line)
                log_time = datetime.fromisoformat(entry["timestamp"]).replace(tzinfo=IST)
                if start <= log_time <= end:
                    logs.append(entry)

        return logs

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching logs: {str(e)}")




class DescriptionInput(BaseModel): 
    """Model for receiving text input from users."""
    prod_desc_by_user: str

class DescriptionResponse(BaseModel):
    """Response model for AI-generated product description."""
    description: str

class BlogDataInput(BaseModel):
    """Model for receiving text input from users."""
    blog: str

class BlogDataResponse(BaseModel):
    """Model for AI-generated tags for blogs."""
    tags: List[str]

class ImageDataInput(BaseModel):
    """Model for receiving base64-encoded images."""
    image_base64: str

class QuestionGetterInput(BaseModel):
    """Model for receiving title name for generating questions."""
    title: str

class DecisionInput(BaseModel):
    """Model for decision-making based on product name and Q&A."""
    title: str
    initial_prod_description: str
    qnas: str  # Serialized list of answers from the user

class DecisionResponse(BaseModel):
    """Response model for item decision (Recycle or Resell)."""
    decision: str  # Expected values: "resell", "recycle", or "IGN"
    guide:dict# Optional[Dict[str, Dict[str, list]]]=None


class ImageDataResponse(BaseModel):
    """Response model for e-waste categorization."""
    title: str
    desc: str
    search_tags: List[str] | None = None
    category: str


class QuestionGetterResponse(BaseModel):
    """Response model for AI-generated questions."""
    questions: List[str]

@app.post("/ai/generate_description", response_model=DescriptionResponse)
async def generate_description(data: DescriptionInput, current_user: dict = Depends(get_current_user)):
    """
    Generate a product description from user input.
    - **prod_desc_by_user**: Text of description of the product.
    - **Returns**: A dictionary containing the AI-generated description.
    """
    try:
        return DescriptionResponse(description=generate_product_description(data.prod_desc_by_user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ai/generate_blog_tags", response_model=BlogDataResponse)
async def generate_tags_endpoint(data: BlogDataInput, current_user: dict = Depends(get_current_user)):
    """
    Generate relevant search tags from user input.
    - **blog**: Text of the blog.
    - **Returns**: A dictionary containing a list of AI-generated tags.
    """
    try:
        return BlogDataResponse(tags=generate_tags(data.blog))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ai/categorize_ewaste_base64", response_model=ImageDataResponse)
async def categorize_e_waste_base64(image_data: ImageDataInput, current_user: dict = Depends(get_current_user)):
    """
    Categorize an e-waste item based on an image.
    - **image_base64**: Base64-encoded image.
    - **Returns**: A dictionary with title, description, search tags, and generic tag.
    """
    try:
        image_bytes = base64.b64decode(image_data.image_base64)
        c=categorize_ewaste_image(image_bytes)
        return ImageDataResponse(title=c['category'],desc=c['desc'],search_tags=c['search_tags'],category=c['generic_tag'])
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/ai/get_questions", response_model=QuestionGetterResponse)
async def gen_ques(data: QuestionGetterInput, current_user: dict = Depends(get_current_user)):
    """
    Generate relevant questions based on the product name.
    - **title**: Name of the product.
    - **Returns**: A list of AI-generated questions.
    """
    try:
        return QuestionGetterResponse(questions=give_ques(data.title)['questions'])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/chatlv")
async def chat_endpoint(websocket: WebSocket):
    """WebSocket endpoint for live chat functionality."""
    try:
        await websocket_endpoint(websocket)
    except Exception as e:
        await websocket.close()

@app.post("/ai/decide", response_model=DecisionResponse)
async def decide_resell_or_recycle(data: DecisionInput, current_user: dict = Depends(get_current_user)):
    """
    Decide whether a product should be recycled or resold.
    - **title**: Name of the product.
    - **initial_prod_description**: Initial product description generated by AI after clicking the photo.
    - **qnas**: List of answers related to the product's condition.
    - **Returns**: Decision ('recycle' or 'resell') with optional guidance in JSON format.
    """
    try:
        decision = decide_recycle_or_resell(data.title, data.initial_prod_description, data.qnas)
        return DecisionResponse(decision=decision["r"], guide=decision["g"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


# from fastapi import FastAPI
# from fastapi.responses import RedirectResponse

# app = FastAPI()

# TARGET_URL = "https://github.com/Akshit2807/e_waste_app/releases/latest"

# @app.get("/")
# def redirect_to_github():
#     return RedirectResponse(url=TARGET_URL, status_code=302)

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)
