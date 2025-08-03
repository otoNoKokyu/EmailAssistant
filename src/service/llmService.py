import ast
from datetime import datetime
import json
import re
import logging
logger = logging.getLogger(__name__)
from src.external.llm import Gemini
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.prompts.emailPrompts import system_prompt,satisfaction_question
from src.service.emailService import EmailAssistant
import json
import ast
import re
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage

class LLM():
    def __init__(self,llm_client = None):
        self.llm_client = llm_client or Gemini()

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

    def extract_json(self,text: str):
        match = re.search(r"```(?:json)?\n([\s\S]*?)```", text)
        try:
            return json.loads(match.group(1) if match else text.strip())
        except:
            return None
    
    def invokeLLM(self, prompt: str, jsonSerialize: bool = False):
        data = self.llm_client.call(prompt)
        return self.extract_json(data) if jsonSerialize else data


class AgentOrchestrator(LLM):
    def __init__(self):
        super().__init__()
    
    def getEmailActions(self,user_query:str):
        return self.__getEmailAgentSchema(system_prompt,user_query)
    
    def __getEmailAgentSchema(self, sys_prompt: str, user_query: str):
        current_time = datetime.now().isoformat()
        full_system_prompt = f"{sys_prompt}\n\nCurrent time: {current_time}"
        messages = [
            SystemMessage(content=full_system_prompt),
            HumanMessage(content=user_query)
        ]
        return self.invokeLLM(messages,True)
    
    @staticmethod
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
    
class EmailAgent:
    def __init__(self, emailProvider: EmailAssistant, orchester: AgentOrchestrator ):
        self.local_action_result = {}
        self.provider = emailProvider
        self.orchester = orchester

    # def run(self):
    #     """Entry point to process all actions."""
    #     return self._process_actions(self.actions)

    def run(self, action_list):
        for action in action_list:
            handler = getattr(self, f"_handle_{action['type']}", None)
            if handler:
                handler(action)
            else:
                self._handle_unknown(action)

    def _handle_search_emails(self, action):
        queries = [action["params"]["query"]] + action["params"].get("query_variants", [])
        emails = {"results": []}
        for q in queries:
            emails = self.provider.search_emails(q, action["params"].get("max_results", 10))
            if emails["results"]:
                break
        if not emails["results"]:
            logger.info("No matching emails found for any query variant.")
            return
        self.local_action_result[action["id"]] = json.dumps(emails["results"], indent=2)
        if len(self.actions) == 1:
            return self._summarize_emails(emails["results"], self.query)

    def _handle_send_email(self, action):
        self.provider.send_email(
            action["params"]["to"],
            action["params"]["subject"],
            action["params"]["body"],
        )

    def _handle_schedule_meeting(self, action):
        logger.info(
            f"Scheduling meeting with {action['params']['with']} on {action['params']['datetime']}"
        )

    def _handle_summarize(self, action):
        logger.info("Summarizing results from:", action["params"]["email_ref"])

    def _handle_conditional(self, action):
        c = action["condition"]
        depends_on_id = c["depends_on"]
        result_raw = self.local_action_result.get(depends_on_id, "[]")
        result = json.loads(result_raw)
        prompt = self.orchester.create_satisfaction_prompt(self.query, result)
        does_satisfy = self.orchester.invokeLLM(prompt)
        if bool(does_satisfy) == c["if"].get("found"):
            branch = c["then"]
        else:
            branch = self._retry_query_variants(depends_on_id, c)
        for b in branch:
            if b["type"] == "reply_email":
                b["depends_on"] = depends_on_id
        self._process_actions(branch)

    def _retry_query_variants(self, depends_on_id, condition):
        search_action = next(
            (a for a in self.actions if a["id"] == depends_on_id and a["type"] == "search_emails"),
            None
        )
        satisfied = False
        result = []
        if search_action:
            queries = search_action["params"].get("query_variants", [])
            for q in queries:
                result_obj = self.provider.search_emails(q, search_action["params"].get("max_results", 10))
                result = result_obj["results"]
                if not result:
                    continue
                self.local_action_result[depends_on_id] = json.dumps(result, indent=2)
                prompt = self.orchester.create_satisfaction_prompt(self.query, result)
                does_satisfy = self.orchester.invokeLLM(prompt)
                if bool(does_satisfy) == condition["if"].get("found"):
                    satisfied = True
                    break
        return condition["then"] if satisfied else condition["else"]

    def _handle_reply_email(self, action):
        result = json.loads(self.local_action_result.get(action["depends_on"], "[]"))
        if not result:
            logger.info("No email found to reply to.")
            return
        email = result[0]
        self.provider.send_reply(
            email["from"],
            email["subject"],
            action["params"]["body"],
            email["message_id"]
        )

    def _handle_unknown(self, action):
        logger.info(f"Unknown action type: {action['type']}")


    