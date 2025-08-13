import ast
from datetime import datetime
import json
import re
import logging
logger = logging.getLogger(__name__)
from src.external.llm import Gemini
from langchain_core.messages import SystemMessage, HumanMessage
from src.prompts.emailPrompts import system_prompt,satisfaction_question,summarization_prompt
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


class EmailAgentOrchestrator(LLM):
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
        l = '\n'.join(i.strip() for i in result if i.strip())
        prompt_sections = [
            "\n### user_query ###",
            user_query,
            "\n### reuslt ###",
            l,
            "\n### QUESTION ###",
            satisfaction_question.strip()
        ]
        return "\n".join(prompt_sections)

    @staticmethod
    def create_summarize_prompt(content: str, q: str):
        prompt = summarization_prompt.format(content=content,q=q)
        return prompt
    
    def doesSatisfyUserQuery(self,user_query:str,result:list[any]):
        satisfaction_prompt =  self.create_satisfaction_prompt(user_query,result)
        return self.invokeLLM(satisfaction_prompt)
    
# class EmailAgent:
#     def __init__(self, emailProvider: EmailAssistant, orchester: EmailAgentOrchestrator,query: str):
#         self.local_action_result = {}
#         self.provider = emailProvider
#         self.orchester = orchester
#         self.query = query

#     async def run(self, action_list):
#         logger.log(1,msg=action_list)
#         self.actions = action_list['actions']
#         for action in action_list['actions']:
#             handler = getattr(self, f"_handle_{action['type']}", None)
#             if handler:
#                 return await handler(action)
#             else:
#                 self._handle_unknown(action)
#         return self.local_action_result

#     async def _handle_search_emails(self, action):
#         queries = [action["params"]["query"]] + action["params"].get("query_variants", [])
#         emails = {"results": []}
#         for q in queries:
#             emails = await self.provider.search_emails(q, action["params"].get("max_results", 10))
#             if emails["results"]:
#                 break
#         if not emails["results"]:
#             logger.info("No matching emails found for any query variant.")
#             return 'No matching emails found.Please refine or change your query.'        
#         snippets = [email["snippet"] for email in emails["results"]]        
#         self.local_action_result[action["id"]] = json.dumps(snippets, indent=2)
#         stringified_result = json.dumps(snippets, indent=2)
#         if len(self.actions) == 1:
#             try:
#                 summarize_prompt = self.orchester.create_summarize_prompt(
#                     stringified_result,
#                     self.query
#                 )
#                 summary = self.orchester.invokeLLM(summarize_prompt)
#                 return summary
#             except Exception as e:
#                 print(f"Error creating summarize prompt: {e}")
#         return
#     def _handle_send_email(self, action):
#         self.provider.send_email(
#             action["params"]["to"],
#             action["params"]["subject"],
#             action["params"]["body"],
#         )

#     def _handle_schedule_meeting(self, action):
#         logger.info(
#             f"Scheduling meeting with {action['params']['with']} on {action['params']['datetime']}"
#         )

#     def _handle_summarize(self, action):
#         logger.info("Summarizing results from:", action["params"]["email_ref"])

#     def _handle_conditional(self, action):
#         c = action["condition"]
#         depends_on_id = c["depends_on"]
#         result_raw = self.local_action_result.get(depends_on_id, "[]")
#         result = json.loads(result_raw)
#         prompt = self.orchester.create_satisfaction_prompt(self.query, result)
#         does_satisfy = self.orchester.invokeLLM(prompt)
#         if bool(does_satisfy) == c["if"].get("found"):
#             branch = c["then"]
#         else:
#             branch = self._retry_query_variants(depends_on_id, c)
#         for b in branch:
#             if b["type"] == "reply_email":
#                 b["depends_on"] = depends_on_id
#         self._process_actions(branch)

#     def _retry_query_variants(self, depends_on_id, condition):
#         search_action = next(
#             (a for a in self.actions if a["id"] == depends_on_id and a["type"] == "search_emails"),
#             None
#         )
#         satisfied = False
#         result = []
#         if search_action:
#             queries = search_action["params"].get("query_variants", [])
#             for q in queries:
#                 result_obj = self.provider.search_emails(q, search_action["params"].get("max_results", 10))
#                 result = result_obj["results"]
#                 if not result:
#                     continue
#                 self.local_action_result[depends_on_id] = json.dumps(result, indent=2)
#                 prompt = self.orchester.create_satisfaction_prompt(self.query, result)
#                 does_satisfy = self.orchester.invokeLLM(prompt)
#                 if bool(does_satisfy) == condition["if"].get("found"):
#                     satisfied = True
#                     break
#         return condition["then"] if satisfied else condition["else"]

#     def _handle_reply_email(self, action):
#         result = json.loads(self.local_action_result.get(action["depends_on"], "[]"))
#         if not result:
#             logger.info("No email found to reply to.")
#             return
#         email = result[0]
#         self.provider.send_reply(
#             email["from"],
#             email["subject"],
#             action["params"]["body"],
#             email["message_id"]
#         )

#     def _handle_unknown(self, action):
#         logger.info(f"Unknown action type: {action['type']}")


import json
import logging

logger = logging.getLogger(__name__)

class EmailAgent:
    def __init__(self, emailProvider: EmailAssistant, orchester, query: str):
        self.local_action_result = {}
        self.provider = emailProvider
        self.orchester = orchester
        self.query = query
        self.final_results = []

    async def run(self, action_list):
        logger.log(1, msg=action_list)
        
        if not action_list or 'actions' not in action_list:
            return "No actions provided."
        
        self.actions = action_list['actions']
        
        # Process all actions
        for action in self.actions:
            try:
                handler = getattr(self, f"_handle_{action['type']}", None)
                if handler:
                    await handler(action)
                else:
                    self._handle_unknown(action)
            except Exception as e:
                error_msg = f"Error processing action {action.get('id', 'unknown')}: {str(e)}"
                logger.error(error_msg)
                self.final_results.append(error_msg)
        
        # Determine return based on action types
        return self._generate_final_response()

    def _generate_final_response(self):
        """Generate final response based on action types and results"""
        action_types = [action['type'] for action in self.actions]
        # If only search actions, return summarized data
        if all(action_type == 'search_emails' for action_type in action_types):
            return self._generate_search_summary()
        
        # For mixed or non-search actions, return status messages
        if self.final_results:
            return "\n".join(self.final_results)
        else:
            return "All actions completed successfully."

    def _generate_search_summary(self):
        """Generate summarized response for search-only actions"""
        all_snippets = []
        
        # Collect all search results
        for action_id, result in self.local_action_result.items():
            try:
                snippets = json.loads(result)
                if isinstance(snippets, list):
                    all_snippets.extend(snippets)
            except (json.JSONDecodeError, TypeError):
                continue
        
        if not all_snippets:
            return "No matching emails found for your query."
        
        # Create summary using orchestrator
        try:
            stringified_result = json.dumps(all_snippets, indent=2)
            summarize_prompt = self.orchester.create_summarize_prompt(
                stringified_result,
                self.query
            )
            summary = self.orchester.invokeLLM(summarize_prompt)
            return summary
        except Exception as e:
            logger.error(f"Error creating summary: {e}")
            return f"Found {len(all_snippets)} emails but failed to summarize."

    async def _handle_search_emails(self, action):
        """Handle email search and store results"""
        action_id = action.get("id", "search_unknown")
        params = action.get("params", {})
        
        main_query = params.get("query", "")
        query_variants = params.get("query_variants", [])
        max_results = params.get("max_results", 10)
        
        queries = [main_query] + query_variants
        emails = {"results": []}
        
        # Try each query until we find results
        for q in queries:
            if not q:  # Skip empty queries
                continue
            try:
                emails = await self.provider.search_emails(q, max_results)
                if emails and emails.get("results"):
                    break
            except Exception as e:
                logger.error(f"Error searching with query '{q}': {e}")
                continue
        
        # Store results in local state
        if emails.get("results"):
            snippets = [email.get("snippet", "") for email in emails["results"]]
            self.local_action_result[action_id] = json.dumps(snippets, indent=2)
            logger.info(f"Found {len(snippets)} emails for action {action_id}")
        else:
            self.local_action_result[action_id] = json.dumps([])
            logger.info(f"No matching emails found for action {action_id}")

    async def _handle_send_email(self, action):
        """Handle email sending"""
        action_id = action.get("id", "send_unknown")
        params = action.get("params", {})
        
        try:
            to = params.get("to", "")
            subject = params.get("subject", "")
            body = params.get("body", "")
            
            if not to or not body:
                error_msg = f"Missing required parameters for send email action {action_id}"
                self.final_results.append(error_msg)
                return
            
            await self.provider.send_email(to, subject, body,self.provider.email)
            success_msg = f"Email sent successfully"
            self.final_results.append(success_msg)
            self.local_action_result[action_id] = success_msg
            
        except Exception as e:
            error_msg = f"Failed to send email: {str(e)}"
            self.final_results.append(error_msg)
            self.local_action_result[action_id] = error_msg

    async def _handle_schedule_meeting(self, action):
        """Handle meeting scheduling"""
        action_id = action.get("id", "schedule_unknown")
        params = action.get("params", {})
        
        try:
            with_person = params.get("with", "")
            datetime = params.get("datetime", "")
            
            if not with_person or not datetime:
                error_msg = f"Missing required parameters for schedule meeting action {action_id}"
                self.final_results.append(error_msg)
                return
            
            # Assuming provider has schedule_meeting method
            await self.provider.schedule_meeting(with_person, datetime)
            success_msg = f"Meeting scheduled with {with_person} on {datetime}"
            self.final_results.append(success_msg)
            self.local_action_result[action_id] = success_msg
            
        except Exception as e:
            error_msg = f"Failed to schedule meeting: {str(e)}"
            self.final_results.append(error_msg)
            self.local_action_result[action_id] = error_msg

    async def _handle_reply_email(self, action):
        """Handle email reply"""
        action_id = action.get("id", "reply_unknown")
        params = action.get("params", {})
        depends_on = action.get("depends_on", "")
        
        try:
            # Get the email to reply to from dependent action
            if not depends_on or depends_on not in self.local_action_result:
                error_msg = f"Reply action {action_id} missing dependency {depends_on}"
                self.final_results.append(error_msg)
                return
            
            result_raw = self.local_action_result.get(depends_on, "[]")
            result = json.loads(result_raw)
            
            if not result:
                error_msg = "No email found to reply to"
                self.final_results.append(error_msg)
                return
            
            email = result[0] if isinstance(result, list) else result
            body = params.get("body", "")
            
            if not body:
                error_msg = f"Missing reply body for action {action_id}"
                self.final_results.append(error_msg)
                return
            
            await self.provider.send_reply(
                email.get("from", ""),
                email.get("subject", ""),
                body,
                email.get("message_id", "")
            )
            
            success_msg = f"Reply sent successfully to {email.get('from', 'unknown')}"
            self.final_results.append(success_msg)
            self.local_action_result[action_id] = success_msg
            
        except Exception as e:
            error_msg = f"Failed to send reply: {str(e)}"
            self.final_results.append(error_msg)
            self.local_action_result[action_id] = error_msg

    async def _handle_conditional(self, action):
        """Handle conditional actions"""
        action_id = action.get("id", "conditional_unknown")
        condition = action.get("condition", {})
        
        try:
            depends_on_id = condition.get("depends_on", "")
            
            if not depends_on_id or depends_on_id not in self.local_action_result:
                error_msg = f"Conditional action {action_id} missing dependency {depends_on_id}"
                self.final_results.append(error_msg)
                return
            
            # Get the result from dependent action
            result_raw = self.local_action_result.get(depends_on_id, "[]")
            result = json.loads(result_raw)
            
            # Check if condition is satisfied
            prompt = self.orchester.create_satisfaction_prompt(self.query, result)
            does_satisfy = self.orchester.invokeLLM(prompt)
            
            # Determine which branch to execute
            if bool(does_satisfy) == condition.get("if", {}).get("found", True):
                branch_actions = condition.get("then", [])
            else:
                # Try query variants if available
                branch_actions = await self._retry_query_variants(depends_on_id, condition)
            
            # Process branch actions
            await self._process_branch_actions(branch_actions, depends_on_id)
            
        except Exception as e:
            error_msg = f"Error in conditional action {action_id}: {str(e)}"
            self.final_results.append(error_msg)
            self.local_action_result[action_id] = error_msg

    async def _retry_query_variants(self, depends_on_id, condition):
        """Retry with query variants if original search didn't satisfy condition"""
        search_action = next(
            (a for a in self.actions if a.get("id") == depends_on_id and a.get("type") == "search_emails"),
            None
        )
        
        if not search_action:
            return condition.get("else", [])
        
        query_variants = search_action.get("params", {}).get("query_variants", [])
        max_results = search_action.get("params", {}).get("max_results", 10)
        
        for q in query_variants:
            try:
                result_obj = await self.provider.search_emails(q, max_results)
                result = result_obj.get("results", [])
                
                if not result:
                    continue
                
                # Update the local state with new results
                snippets = [email.get("body_clean", "") for email in result]
                self.local_action_result[depends_on_id] = json.dumps(snippets, indent=2)
                
                # Check if this satisfies the condition
                prompt = self.orchester.create_satisfaction_prompt(self.query, result)
                does_satisfy = self.orchester.invokeLLM(prompt)
                
                if bool(does_satisfy) == condition.get("if", {}).get("found", True):
                    return condition.get("then", [])
                    
            except Exception as e:
                logger.error(f"Error retrying with query variant '{q}': {e}")
                continue
        
        return condition.get("else", [])

    async def _process_branch_actions(self, branch_actions, depends_on_id):
        """Process actions from conditional branches"""
        for branch_action in branch_actions:
            # Set dependency for reply actions
            if branch_action.get("type") == "reply_email":
                branch_action["depends_on"] = depends_on_id
            
            # Process the branch action
            handler = getattr(self, f"_handle_{branch_action['type']}", None)
            if handler:
                await handler(branch_action)
            else:
                self._handle_unknown(branch_action)

    def _handle_unknown(self, action):
        """Handle unknown action types"""
        action_type = action.get("type", "unknown")
        action_id = action.get("id", "unknown")
        error_msg = f"Unknown action type '{action_type}' for action {action_id}"
        logger.warning(error_msg)
        self.final_results.append(error_msg)
    