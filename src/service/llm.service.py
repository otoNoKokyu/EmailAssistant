import ast
from datetime import datetime
import json
import re
from src.external.llm import Gemini
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from prompts.emailSchemaPrompt import system_prompt,satisfaction_question
import json
import ast
import re
from typing import TypeVar, List
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage

class LLM(Gemini):
    def __init__(self):
        super().__init__()

    def extract_first_dict_from_response(self, response: str):
        code_blocks = re.findall(r"```(?:json)?\n([\s\S]*?)```", response)
        
        for block in code_blocks:
            try:
                return json.loads(block)
            except Exception:
                pass
            try:
                return ast.literal_eval(block)
            except Exception:
                pass
            try:
                fixed = block.replace("'", '"')
                return json.loads(fixed)
            except Exception:
                continue

        # Fallback: find first dict by brute-force
        start = response.find('{')
        if start == -1:
            return None

        brace_count = 0
        for i in range(start, len(response)):
            if response[i] == '{':
                brace_count += 1
            elif response[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    dict_str = response[start:i+1]
                    try:
                        return json.loads(dict_str)
                    except:
                        pass
                    try:
                        return ast.literal_eval(dict_str)
                    except:
                        try:
                            dict_str_fixed = dict_str.replace("'", '"')
                            return json.loads(dict_str_fixed)
                        except:
                            return None
        return None

    def invokeLLM(self,prompt:str):
        return self.extract_first_dict_from_response(self.client.generate_content(prompt).text)


    def getEmailAgentSchema(self, sys_prompt: str, user_query: str):
        current_time = datetime.now().isoformat()
        full_system_prompt = f"{sys_prompt}\n\nCurrent time: {current_time}"
        messages = [
            SystemMessage(content=full_system_prompt),
            HumanMessage(content=user_query)
        ]
        return self.extract_first_dict_from_response(self.client.generate_content(messages).text)
        

class EmailAgent(LLM):
    def __init__(self):
        super().__init__()
    
    def fetchActions(self,user_query:str):
        return self.getEmailAgentSchema(system_prompt,user_query)
    
    def create_satisfaction_prompt(user_query: str, result: str) -> str:
        prompt_sections = [
            "\n### user_query ###",
            user_query,
            "\n### reuslt ###",
            result.strip(),
            "\n### QUESTION ###",
            satisfaction_question.strip()
        ]
        return "\n".join(prompt_sections)

    def doesSatisfyUserQuery(self,user_query:str,result:list[any]):
        satisfaction_prompt =  self.create_satisfaction_prompt(user_query,result)
        return self.invokeLLM(satisfaction_prompt)


    