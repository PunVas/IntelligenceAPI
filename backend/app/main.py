from fastapi import FastAPI, HTTPException, Depends, WebSocket, Request, Response, Query
from pydantic import BaseModel
from typing import List
import base64
import json
import datetime
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse
from zoneinfo import ZoneInfo

# Import services and authentication
from app.auth.jwt_handler import get_current_user
from app.services.ai_service import (
    generate_product_description,
    generate_tags,
    categorize_ewaste_image,
    decide_recycle_or_resell,
    give_ques,
    websocket_endpoint,
)

# Initialize FastAPI
app = FastAPI()

# Set up logging
logging.basicConfig(filename="logs.json", level=logging.INFO, format="%(message)s")

IST = ZoneInfo("Asia/Kolkata")  # India's timezone

class LogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = datetime.datetime.now(datetime.UTC)

        # Read request body safely
        try:
            body_bytes = await request.body()
            request_body = body_bytes.decode("utf-8") if body_bytes else None
        except Exception as e:
            request_body = f"Error reading body: {str(e)}"

        request_data = {
            "time": start_time.isoformat(),
            "method": request.method,
            "url": str(request.url),
            "headers": {k: v for k, v in request.headers.items()},
            "body": request_body
        }

        response_body = b""  # Default empty response body
        status_code = 500  # Default status code in case of failure
        headers = {}  # Default empty headers

        try:
            response = await call_next(request)

            # Capture response body
            response_body = b"".join([chunk async for chunk in response.body_iterator])
            response_content = response_body.decode("utf-8") if response_body else None

            # Preserve response details
            status_code = response.status_code
            headers = dict(response.headers)

            request_data["status_code"] = status_code
            request_data["response_body"] = response_content

        except Exception as e:
            request_data["error"] = str(e)
            logging.error(json.dumps(request_data))

            # Create an error response
            response_body = json.dumps({"detail": "Internal Server Error"}).encode("utf-8")
            status_code = 500
            headers = {"Content-Type": "application/json"}

        logging.info(json.dumps(request_data))

        # Always return a response
        return StreamingResponse(iter([response_body]), status_code=status_code, headers=headers)


app.add_middleware(LogMiddleware)


@app.get("/logs")
async def get_logs(
    start_time: str = Query(..., description="Start time in YYYY-MM-DDTHH:MM:SS format (IST)"),
    end_time: str = Query(..., description="End time in YYYY-MM-DDTHH:MM:SS format (IST)")
):
    """Fetch logs between a given time range (Input time in IST)."""
    try:
        start_utc = datetime.datetime.fromisoformat(start_time).replace(tzinfo=IST).astimezone(datetime.UTC)
        end_utc = datetime.datetime.fromisoformat(end_time).replace(tzinfo=IST).astimezone(datetime.UTC)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DDTHH:MM:SS")

    logs = []
    with open("logs.json", "r") as log_file:
        for line in log_file:
            log_entry = json.loads(line)
            log_time = datetime.datetime.fromisoformat(log_entry["time"])
            if start_utc <= log_time <= end_utc:
                logs.append(log_entry)

    return {"logs": logs}



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
    decision: str
    guide: dict  # Optional additional guidance if applicable

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
        return ImageDataResponse(title=c['category'],desc=c['desc'],search_tags=c['search_tags'],category=c['category'])
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
    


