from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
from abc import ABC, abstractmethod
import os


class AbstractLLM(ABC):
    @abstractmethod
    def call(self, prompt: str):
        pass

class Gemini(AbstractLLM):
    def __init__(self):
        load_dotenv()
        self.__client = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            timeout=None,
            api_key=os.getenv("GEMINI_API_KEY"),
        )

    def call(self, prompt: str):
        return self.__client.invoke(prompt).content
        
    