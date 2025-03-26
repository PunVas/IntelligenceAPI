from google import genai
import google.generativeai as genaiLive
from fastapi import HTTPException, WebSocket
import json
import re
import os
from typing import List
from PIL import Image
import io

GEMINI_API_KEY = "AIzaSyAvf4M4bnHDafmysUJQTDASCHwIZnou-uE"
USE_MODEL = "gemini-2.0-flash"
client = genai.Client(api_key=GEMINI_API_KEY)
genaiLive.configure(api_key=GEMINI_API_KEY)
model = genaiLive.GenerativeModel(USE_MODEL)

def decide_recycle_or_resell(product_name: str, product_desc: str, user_answers: str) -> dict:
    try:
        system_prompt = (
            f"You are an AI that determines whether an item should be 'resold' or 'recycled' based on its condition, functionality, and completeness of information. "
            f"The product is '{product_name}', and the initial item description is: {product_desc}. "
            f"The user has provided the following answers to relevant questions: {user_answers}. "
            "Carefully analyze the answers and follow these strict rules: "
            "- Return 'resell' **only if ALL key details** (physical condition, battery life, full functionality of components, and complete specifications including processor, RAM, and storage) are provided and indicate the item is in excellent or good working condition. Judge strictly based on the technically correct answers to the questions. "
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
            )

        elif response_text == "resell":
            return {"r": "resell", "g": "Congrats! Your item is fit for resell! 🎉"}

        else:
            return {"r": "IGN", "g": "IGN"}

        guide_response = client.models.generate_content(
            model="gemini-2.0-flash", contents=[guide_prompt, user_input]
        )
        guide_text = guide_response.text.strip("```").strip("json").strip("\n") if hasattr(guide_response, "text") else str(guide_response).strip("```").strip("json").strip("\n")

        # try:
        #     guide_json = json.loads(guide_text)
        # except json.JSONDecodeError:
        #     guide_json = {"initials": "Recycling instructions not available.", "pointers": {}}
        guide_json=dict(json.loads(guide_text))

        return {"r": response_text, "g": guide_json}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google API error: {str(e)}")
    
print(decide_recycle_or_resell("earphones","This is a boAt eardope with dual tone case","""Q. How old are the earphones and what is their model number? A. 2 years Q. What is the current functional condition of the earphones? Do both ears work correctly, and are there any issues with sound quality (e.g., distortion, static, imbalance)? A. yes works fine Q. Have you attempted any repairs or modifications on the earphones? If so, what was done? A. No Q. What is the overall cosmetic condition of the earphones, including any scratches, dents, or discoloration? Are all original accessories (e.g., ear tips, carrying case) included and in good condition? A. yes"""))