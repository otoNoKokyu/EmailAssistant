from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv
import os

class Gemini:
    _client = None
    def __init__(self):
        load_dotenv()
        self._client = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            timeout=None,
            api_key=os.getenv("GEMINI_API_KEY"),
        )
    @property
    def client(self):
        return self._client
        