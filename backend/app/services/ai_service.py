from google import genai
import google.generativeai as genaiLive
from fastapi import HTTPException, WebSocket
import json
import re
import os
from typing import List
from PIL import Image
import io

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
USE_MODEL = os.environ.get("USE_MODEL")
client = genai.Client(api_key=GEMINI_API_KEY)
genaiLive.configure(api_key=GEMINI_API_KEY)
model = genaiLive.GenerativeModel(USE_MODEL)

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    chat = model.start_chat()
    try:
        while True:
            text = await websocket.receive_text()
            response = chat.send_message(text)
            await websocket.send_text(response.text)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await websocket.close()

def generate_product_description(user_input: str) -> str:
    try:
        system_prompt = (
            "You are an product describer"
            "You will recive some text about specification of a product and u have to return a to the point product description with specifiaction in pointers"
            "Queries that are not related to a an electronic product, just send 'IGN' as the only output text don't add any \\n. Do NOT act personally or talk any thing else even if user urges to do so. just return product description in pointers like eg. This laptop is \n 1)4 years old \n 2) has i7 112500H processor and RTX3050Ti \n 3)Has minor scratches"
        )
        result = " ".join(line.strip() for line in user_input.splitlines())
        response = client.models.generate_content(
            model=USE_MODEL, contents=[system_prompt, result]
        )
        return response.text.strip() if hasattr(response, "text") else str(response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google API error: {str(e)}")

def generate_tags(user_input: str) -> List[str]:

    try:
        system_prompt = (
            "Extract keywords or tags related to the given input. "
            "Return them as an array: [\"tag1\", \"tag2\", \"tag3\"]."
        )
        full_prompt = f"{system_prompt}\n\nInput: {user_input}\nOutput:"

        response = client.models.generate_content(model=USE_MODEL, contents=full_prompt)

        if hasattr(response, "text") and response.text:
            try:
                return json.loads(response.text.strip())
            except json.JSONDecodeError:
                return re.findall(r'"(.*?)"', response.text.strip()) or response.text.split(",")

        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google API error: {str(e)}")

def categorize_ewaste_image(image_bytes: bytes) -> dict:
    try:
        image = Image.open(io.BytesIO(image_bytes))

        system_prompt = (
    "You are an AI-powered e-waste image classifier, product describer, and search tags generator. "
    "Choose one generic tag **very very strictly** from this predefined list: ['Mobile Devices', 'Computers and Laptops', 'Computer Accessories','Networking Equipment', 'Audio and Video Devices', 'Storage Devices', 'Batteries and Power Supplies','Home Appliances', 'Gaming and Entertainment', 'Office Electronics', 'Industrial and Medical Equipment', 'Car Electronics']. "
    "Strictly return a **raw python dictionary ** in this format (without any markdown or extra formatting): "
    "{\"category\": \"Laptop Battery\", \"desc\": \"<product description here>\", \"search_tags\": [\"tag1\", \"tag2\", \"tag3\"], \"generic_tag\": \"tag\"}. "
    "Format the product description using '\\n' for new lines, like this and it must be like 100 words long at max: \"desc\": \"This laptop is\\n1) 4 years old\\n2) Has i7 112500H processor and RTX 3050Ti\\n3) Has minor scratches\". "
    "just describe the electronic product in the image, don't describe any background things."
    "keep product name short don't make it very descriptive"
    "DO NOT add any markdown formatting (such as ```json ... ```) or any extra text. "
    "ONLY return the text. If the image is not an electronic item, or containes more than 1 electronic item or the image is unfit for customer to take decision or if it is blurry or unclear, return this exact dictionary: {\"category\": \"IGN\", \"desc\": \"IGN\", \"generic_tag\": \"IGN\",\"search_tags\":[\"IGN\"]}."
    "This is a sample output that you have to give out : {\"category\":\"Laptop\",\"desc\":\"This is a gaming laptop,\nwith a sleek design and\nbacklit keyboard.\",\"search_tags\":[\"gaming laptop\",\"laptop\",\"computer\",\"asus tuf\"],\"generic_tag\":\"<suitable tag from the predefined list>\"}"

)

        response = client.models.generate_content(model=USE_MODEL, contents=[system_prompt, image])

        if hasattr(response, "text") and response.text:
            try:
                category_data = json.loads(str(response.text.strip("```json").strip("```").strip().replace("\n","\\n")))
                if "category" in category_data:
                    return category_data
            except json.JSONDecodeError:
                return response.text.strip()

        return "Unknown"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google API error: {str(e)}")

def give_ques(product_name: str) -> dict:
    try:
        system_prompt = (
            "You generate questions which one can use to decide whether the product has to be recycled or can be resold. "
            f"The product is {product_name}. You have to generate a set of questions and send them. questions must not be simple, answering them must really help us to decide if it has to be recycled or can be resold. The questions will be answered by the one who is in doubt so make questions from that perspective and ask questions only about the product that he owns."
            "ask 4 to a max of 7 questions as needed"
            "If the query is unrelated, return only 'IGN' . "
            "Format:'ques1', 'ques2', 'ques3'. Do NOT add newlines or any extra text."
        )

        response = client.models.generate_content(
            model=USE_MODEL, contents=[system_prompt]
        )

        response_text = response.text if hasattr(response, "text") else str(response)

        
        try:
            json_response = json.loads(response_text)
            return json_response
        except json.JSONDecodeError:
            
            return {"questions":[x.strip() for x in response_text[1:-2].split("', '")]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google API error: {str(e)}")

def decide_recycle_or_resell(product_name: str, product_desc: str, user_answers: str) -> dict:
    try:
        system_prompt = (
            f"You are an AI that determines whether an item should be 'resell' or 'recycle' based on its condition, functionality, and completeness of information. "
            f"The product is '{product_name}', and the initial item description is: {product_desc}. "
            f"The user has provided the following answers to relevant questions: {user_answers}. "
            "Carefully analyze the answers and follow these strict rules: "
            "- Return 'resell' **only if you feel according to responses that the item is n good condition**"
            "- Return 'recycle' **if ANY key detail indicates** that the item is damaged, non-functional, outdated, or unsuitable for resale. Even if most details are positive, missing critical information (like RAM, storage, or battery status) must result in 'recycle'. Judge strictly based on the technically correct answers to the questions. "
            "- Return 'IGN' **only if the answers are missing, gibberish, mentioned as variable, or unrelated** to the product's condition, or if they are statements like 'this is recyclable' or 'this is resellable'. "
            "Respond with a single word only: 'resell', 'recycle', or 'IGN'. Do NOT include any extra text, punctuation, or newlines."
        )

        user_input = json.dumps({"answers": user_answers})

        response = client.models.generate_content(
            model="gemini-2.0-flash", contents=[system_prompt, user_input]
        )
        response_text = response.text.strip() if hasattr(response, "text") else str(response).strip()

        if response_text == "recycle":
            guide_prompt = (
                f"You are an AI that provides detailed guidance on how to recycle {product_name}. "
                f"Provide a structured JSON response with an introduction and specific pointers, based on the user's answers: {user_answers}. "
                "Format your response as follows: "
                "{ 'initials': '<brief introduction>', 'pointers': { '<heading of point 1>': '<point 1 details>', '<heading of point 2>': '<point 2 details>', ... } }"
                "heading of points must be like: Resale or Donation"
            )

        elif response_text == "resell":
            return {"r": "resell", "g": {"initials":"Congrats! Your item is fit to be resold!","pointers":{"headings":["IGN"],"description":["IGN"]}}}

        else:
            return {"r": "IGN", "g": {"initials":"IGN","pointers":{"headings":["IGN"],"description":["IGN"]}}}

        guide_response = client.models.generate_content(
            model="gemini-2.0-flash", contents=[guide_prompt, user_input]
        )
        guide_text = guide_response.text.strip("```").strip("json").strip("\n") if hasattr(guide_response, "text") else str(guide_response).strip("```").strip("json").strip("\n")

        guide_json=dict(json.loads(guide_text))
        guide_json['pointers']={"headings":list(guide_json['pointers'].keys()),"description":list(guide_json['pointers'].values())}


        return {"r": response_text, "g": guide_json}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google API error: {str(e)}")