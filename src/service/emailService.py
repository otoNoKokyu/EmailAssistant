import smtplib
from email.mime.text import MIMEText
import base64
import re
from typing import List, Dict
from src.models.googleCredential import GoogleCredential
from src.external.email import EmailProvider, GmailProvider
import html
from bs4 import BeautifulSoup, NavigableString, Comment
from typing import Optional, List, Set
import unicodedata


class EmailAssistant:
    def __init__(self, provider: EmailProvider = None,credential_record: GoogleCredential = None):
        self.provider = provider or GmailProvider(credential_record)
        self.email = self.provider.get_email_address()
        self.password = self.provider.get_email_password()
        self.masker = EmailMasker()
        # masked_text = masker.mask_email(clean_email_body)


    async def send_email(self, to_email: str, subject: str, body: str,userEmail: str = None):
        pattern = r"\{\{me\}\}"
        recipient = to_email
        if re.search(pattern, to_email):
            recipient = userEmail   
        else: 
            recipient = await self.find_contact_email(to_email)

        msg = MIMEText(body)
        msg["From"] = self.email
        msg["To"] = recipient
        msg["Subject"] = subject

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:  
            smtp.login(self.email, self.password)
            smtp.send_message(msg)

    async def find_contact_email(self, query: str) -> str:
        service = await self.provider.get_contact_client()
        results = service.otherContacts().list(
            pageSize=1000,
            readMask='names,emailAddresses'
        ).execute()

        contacts = results.get("otherContacts", [])
        contacts.append({"name": "me", "email": self.email})

        pattern = re.compile(query, re.IGNORECASE)

        for person in contacts:
            names = person.get("names", [])
            emails = person.get("emailAddresses", [])
            if not emails:
                continue
            email = emails[0]["value"]
            name = names[0]["displayName"] if names else ""
            if pattern.search(name) or pattern.search(email):
                return email

        return query  # fallback

    async def send_reply(self, to_email: str, subject: str, body: str, reply_to_message_id: str):
        recipient = await self.provider.find_contact_email(to_email)

        msg = MIMEText(body)
        msg["From"] = self.email
        msg["To"] = recipient
        msg["Subject"] = f"Re: {subject}" if not subject.startswith("Re: ") else subject
        msg["In-Reply-To"] = reply_to_message_id
        msg["References"] = reply_to_message_id

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(self.email, self.password)
            smtp.send_message(msg)

    async def search_emails(self, query: str, max_results: int = 0, clean_body: bool = True) -> Dict:
        try:
            gmail_client = await self.provider.get_mail_client()
            response = gmail_client.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()
            
            messages_data = response.get("messages", [])
            messages = []
            cleaner = EmailCleaner() if clean_body else None
            
            for msg in messages_data:
                msg_data = gmail_client.users().messages().get(
                    userId="me", id=msg["id"], format="full"
                ).execute()
                
                headers = {
                    h["name"].lower(): h["value"]
                    for h in msg_data["payload"].get("headers", [])
                }
                
                message_id = headers.get("message-id", "")
                body_content = ""
                clean_body_content = ""
                
                # Extract email body
                if clean_body:
                    body_content = self._extract_email_body(msg_data["payload"])
                    if body_content:
                        clean_body_content = cleaner.clean(body_content)
                    maskedContent = self.masker.mask_email_content(clean_body_content)
                
                messages.append({
                    "id": msg["id"],
                    "subject": headers.get("subject", "No Subject"),
                    "from": headers.get("from", "Unknown"),
                    "to": headers.get("to", "Unknown"),
                    "date": headers.get("date"),
                    "snippet": msg_data.get("snippet", ""),
                    "labels": msg_data.get("labelIds", []),
                    "message_id": message_id,
                    "body_html": body_content if clean_body else None,
                    "body_clean": maskedContent,
                })
            
            return {
                "status": "success",
                "query": query,
                "results": messages,
                "found": len(messages) > 0,
                "body_cleaned": clean_body
            }
        except Exception as e:
            return {
                "status": "error",
                "query": query,
                "error": str(e),
            }

    def _extract_email_body(self, payload) -> str:
        """Extract HTML body from Gmail API payload"""
        body_content = ""
        
        # Handle multipart messages
        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/html":
                    body_data = part.get("body", {}).get("data", "")
                    if body_data:
                        body_content = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                        break
                elif part["mimeType"] == "multipart/alternative" and "parts" in part:
                    for subpart in part["parts"]:
                        if subpart["mimeType"] == "text/html":
                            body_data = subpart.get("body", {}).get("data", "")
                            if body_data:
                                body_content = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                                break
                    if body_content:
                        break
        
        # Handle single part messages
        elif payload["mimeType"] == "text/html":
            body_data = payload.get("body", {}).get("data", "")
            if body_data:
                body_content = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
        
        # Fallback to plain text if no HTML found
        if not body_content:
            if "parts" in payload:
                for part in payload["parts"]:
                    if part["mimeType"] == "text/plain":
                        body_data = part.get("body", {}).get("data", "")
                        if body_data:
                            body_content = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                            break
            elif payload["mimeType"] == "text/plain":
                body_data = payload.get("body", {}).get("data", "")
                if body_data:
                    body_content = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
        
        return body_content



import re
import hashlib
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import RecognizerResult, OperatorConfig
from typing import Dict, List, Optional, Set
import phonenumbers
from urllib.parse import urlparse

class EmailMasker:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EmailMasker, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if EmailMasker._initialized:
            return
            
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        self._setup_patterns()
        self._setup_operators()
        EmailMasker._initialized = True
    
    def _setup_patterns(self):
        self.upi_pattern = re.compile(r'\b[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{3,64}\b')
        self.ssn_pattern = re.compile(r'\b(?:\d{3}-\d{2}-\d{4}|\d{9}|\d{3}\s\d{2}\s\d{4})\b')
        self.passport_pattern = re.compile(r'\b[A-Z]{1,2}\d{6,9}\b')
        self.license_pattern = re.compile(r'\b[A-Z]{1,2}\d{6,8}\b')
        self.account_pattern = re.compile(r'\b(?:account|acct)[\s#:]*(\d{4,20})\b', re.IGNORECASE)
        self.routing_pattern = re.compile(r'\b(?:routing|aba)[\s#:]*(\d{9})\b', re.IGNORECASE)
        self.card_pattern = re.compile(r'\b(?:\d{4}[\s-]?){3}\d{4}\b')
        self.cvv_pattern = re.compile(r'\b(?:cvv|cvc|security code)[\s:]*(\d{3,4})\b', re.IGNORECASE)
        self.pin_pattern = re.compile(r'\b(?:pin|password)[\s:]*(\d{4,8})\b', re.IGNORECASE)
        self.ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
        self.mac_pattern = re.compile(r'\b[0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}\b')
        self.medical_pattern = re.compile(r'\b(?:medical|patient|health)[\s#:]*(\w+\d+|\d+\w+)\b', re.IGNORECASE)
        self.insurance_pattern = re.compile(r'\b(?:policy|insurance)[\s#:]*([A-Z0-9]{6,20})\b', re.IGNORECASE)
        self.bitcoin_pattern = re.compile(r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b')
        self.ethereum_pattern = re.compile(r'\b0x[a-fA-F0-9]{40}\b')
        self.iban_pattern = re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b')
        self.swift_pattern = re.compile(r'\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?\b')
        self.vin_pattern = re.compile(r'\b[A-HJ-NPR-Z0-9]{17}\b')
        self.coordinate_pattern = re.compile(r'\b-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}\b')
        self.doi_pattern = re.compile(r'\b10\.\d{4,}\/[^\s]+\b')
        self.api_key_pattern = re.compile(r'\b[A-Za-z0-9]{20,}\b')
        self.token_pattern = re.compile(r'\b(?:token|key|secret|auth)[\s:=]+([A-Za-z0-9+/]{20,}={0,2})\b', re.IGNORECASE)
        
        self.sensitive_keywords = {
            'financial': ['balance', 'amount', 'payment', 'transaction', 'invoice', 'bill', 'charge'],
            'personal': ['birthday', 'birth date', 'age', 'married', 'divorced', 'spouse'],
            'medical': ['diagnosis', 'treatment', 'medication', 'prescription', 'symptom', 'condition'],
            'legal': ['lawsuit', 'settlement', 'court', 'attorney', 'legal', 'contract'],
            'employment': ['salary', 'wage', 'bonus', 'promotion', 'termination', 'resignation'],
            'education': ['grade', 'gpa', 'transcript', 'degree', 'diploma', 'certification']
        }
    
    def _setup_operators(self):
        self.operators_config = {
            "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
            "PERSON": OperatorConfig("replace", {"new_value": "[PERSON]"}),
            "LOCATION": OperatorConfig("replace", {"new_value": "[LOCATION]"}),
            "ORGANIZATION": OperatorConfig("replace", {"new_value": "[ORGANIZATION]"}),
            "DATE_TIME": OperatorConfig("replace", {"new_value": "[DATE]"}),
            "CREDIT_CARD": OperatorConfig("replace", {"new_value": "[CARD_NUMBER]"}),
            "IBAN_CODE": OperatorConfig("replace", {"new_value": "[IBAN]"}),
            "US_SSN": OperatorConfig("replace", {"new_value": "[SSN]"}),
            "US_PASSPORT": OperatorConfig("replace", {"new_value": "[PASSPORT]"}),
            "US_BANK_NUMBER": OperatorConfig("replace", {"new_value": "[BANK_ACCOUNT]"}),
            "IP_ADDRESS": OperatorConfig("replace", {"new_value": "[IP_ADDRESS]"}),
            "URL": OperatorConfig("replace", {"new_value": "[URL]"}),
            "US_DRIVER_LICENSE": OperatorConfig("replace", {"new_value": "[LICENSE]"}),
            "MEDICAL_LICENSE": OperatorConfig("replace", {"new_value": "[MEDICAL_ID]"}),
            "CRYPTO": OperatorConfig("replace", {"new_value": "[CRYPTO_ADDRESS]"}),
            "AU_ABN": OperatorConfig("replace", {"new_value": "[ABN]"}),
            "AU_ACN": OperatorConfig("replace", {"new_value": "[ACN]"}),
            "AU_TFN": OperatorConfig("replace", {"new_value": "[TFN]"}),
            "AU_MEDICARE": OperatorConfig("replace", {"new_value": "[MEDICARE]"}),
            "UK_NHS": OperatorConfig("replace", {"new_value": "[NHS]"}),
            "IBAN": OperatorConfig("replace", {"new_value": "[IBAN]"}),
            "NRP": OperatorConfig("replace", {"new_value": "[NRP]"}),
            "SG_NRIC_FIN": OperatorConfig("replace", {"new_value": "[NRIC]"}),
            "ES_NIF": OperatorConfig("replace", {"new_value": "[NIF]"}),
            "IT_FISCAL_CODE": OperatorConfig("replace", {"new_value": "[FISCAL_CODE]"}),
            "IT_DRIVER_LICENSE": OperatorConfig("replace", {"new_value": "[IT_LICENSE]"}),
            "IT_VAT_CODE": OperatorConfig("replace", {"new_value": "[VAT_CODE]"}),
            "IT_PASSPORT": OperatorConfig("replace", {"new_value": "[IT_PASSPORT]"}),
            "IT_IDENTITY_CARD": OperatorConfig("replace", {"new_value": "[IT_ID_CARD]"})
        }
    
    def mask_email(self, text: str) -> str:
        if not text or not text.strip():
            return text
        
        try:
            text = self._preprocess_text(text)
            text = self._mask_custom_patterns(text)
            text = self._mask_with_presidio(text)
            text = self._mask_contextual_sensitive_info(text)
            text = self._post_process_text(text)
            return text
        except Exception:
            return self._fallback_mask(text)
    
    def _preprocess_text(self, text: str) -> str:
        text = re.sub(r'\s+', ' ', text)
        text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        return text.strip()
    
    def _mask_custom_patterns(self, text: str) -> str:
        text = self.upi_pattern.sub('[UPI_ID]', text)
        text = self.ssn_pattern.sub('[SSN]', text)
        text = self.passport_pattern.sub('[PASSPORT]', text)
        text = self.license_pattern.sub('[LICENSE]', text)
        text = self.account_pattern.sub(r'\1'[:4] + '[ACCOUNT]', text)
        text = self.routing_pattern.sub('[ROUTING]', text)
        text = self.card_pattern.sub('[CARD_NUMBER]', text)
        text = self.cvv_pattern.sub(r'\1[CVV]', text)
        text = self.pin_pattern.sub(r'\1[PIN]', text)
        text = self.ip_pattern.sub('[IP_ADDRESS]', text)
        text = self.mac_pattern.sub('[MAC_ADDRESS]', text)
        text = self.medical_pattern.sub(r'\1[MEDICAL_ID]', text)
        text = self.insurance_pattern.sub(r'\1[POLICY]', text)
        text = self.bitcoin_pattern.sub('[BITCOIN_ADDRESS]', text)
        text = self.ethereum_pattern.sub('[ETH_ADDRESS]', text)
        text = self.iban_pattern.sub('[IBAN]', text)
        text = self.swift_pattern.sub('[SWIFT_CODE]', text)
        text = self.vin_pattern.sub('[VIN]', text)
        text = self.coordinate_pattern.sub('[COORDINATES]', text)
        text = self.doi_pattern.sub('[DOI]', text)
        text = self.token_pattern.sub(r'\1[API_TOKEN]', text)
        
        api_key_matches = self.api_key_pattern.findall(text)
        for match in api_key_matches:
            if len(match) >= 20 and any(c.isdigit() for c in match) and any(c.isalpha() for c in match):
                text = text.replace(match, '[API_KEY]')
        
        return text
    
    def _mask_with_presidio(self, text: str) -> str:
        try:
            analyzer_results = self.analyzer.analyze(
                text=text,
                language='en',
                score_threshold=0.3,
                return_decision_process=False
            )
            
            if not analyzer_results:
                return text
            
            anonymized_result = self.anonymizer.anonymize(
                text=text,
                analyzer_results=analyzer_results,
                operators=self.operators_config
            )
            
            return anonymized_result.text
        except Exception:
            return text
    
    def _mask_contextual_sensitive_info(self, text: str) -> str:
        words = text.split()
        masked_words = []
        
        for i, word in enumerate(words):
            word_lower = word.lower().strip('.,!?;:')
            masked_word = word
            
            if self._is_sensitive_context(words, i):
                if word_lower in self.sensitive_keywords['financial']:
                    masked_word = '[FINANCIAL_INFO]'
                elif word_lower in self.sensitive_keywords['medical']:
                    masked_word = '[MEDICAL_INFO]'
                elif word_lower in self.sensitive_keywords['personal']:
                    masked_word = '[PERSONAL_INFO]'
                elif word_lower in self.sensitive_keywords['legal']:
                    masked_word = '[LEGAL_INFO]'
                elif word_lower in self.sensitive_keywords['employment']:
                    masked_word = '[EMPLOYMENT_INFO]'
                elif word_lower in self.sensitive_keywords['education']:
                    masked_word = '[EDUCATION_INFO]'
            
            if re.match(r'^\$\d{1,3}(,\d{3})*(\.\d{2})?$', word):
                masked_word = '[AMOUNT]'
            elif re.match(r'^\d{1,3}(,\d{3})*(\.\d{2})?\s*(USD|EUR|GBP|CAD|AUD)$', word, re.IGNORECASE):
                masked_word = '[CURRENCY_AMOUNT]'
            elif word_lower.startswith('http') and self._is_sensitive_url(word):
                masked_word = '[SENSITIVE_URL]'
            elif re.match(r'^[A-Za-z0-9+/]{16,}={0,2}$', word) and len(word) % 4 == 0:
                masked_word = '[ENCODED_DATA]'
            
            masked_words.append(masked_word)
        
        return ' '.join(masked_words)
    
    def _is_sensitive_context(self, words: List[str], index: int) -> bool:
        context_window = 3
        start = max(0, index - context_window)
        end = min(len(words), index + context_window + 1)
        context = ' '.join(words[start:end]).lower()
        
        sensitive_contexts = [
            'confidential', 'private', 'personal', 'secure', 'classified',
            'payment', 'transaction', 'account', 'balance', 'amount',
            'medical', 'health', 'diagnosis', 'treatment', 'prescription',
            'legal', 'attorney', 'court', 'lawsuit', 'contract',
            'salary', 'wage', 'income', 'tax', 'ssn', 'social security'
        ]
        
        return any(keyword in context for keyword in sensitive_contexts)
    
    def _is_sensitive_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url.lower())
            sensitive_domains = [
                'paypal', 'stripe', 'bank', 'credit', 'medical', 'health',
                'private', 'secure', 'confidential', 'personal', 'admin'
            ]
            return any(domain in parsed.netloc for domain in sensitive_domains)
        except:
            return False
    
    def _mask_phone_numbers(self, text: str) -> str:
        try:
            for match in phonenumbers.PhoneNumberMatcher(text, None):
                phone_str = text[match.start:match.end]
                text = text.replace(phone_str, '[PHONE]')
            return text
        except:
            return text
    
    def _post_process_text(self, text: str) -> str:
        text = re.sub(r'\[(\w+)\]\s*\[\1\]', r'[\1]', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _fallback_mask(self, text: str) -> str:
        try:
            text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
            text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', text)
            text = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[CARD_NUMBER]', text)
            text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', text)
            text = re.sub(r'\$\d{1,3}(,\d{3})*(\.\d{2})?', '[AMOUNT]', text)
            return text
        except:
            return text

    def mask_email_content(self,text: str) -> str:
        return self.mask_email(text)



class EmailCleaner:
    
    _instance = None
    _initialized = False
    
    def __new__(cls, preserve_formatting: bool = False, remove_signatures: bool = True, 
                min_content_length: int = 5, max_content_length: int = 500000):
        if cls._instance is None:
            cls._instance = super(EmailCleaner, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, preserve_formatting: bool = False, remove_signatures: bool = True, 
                 min_content_length: int = 5, max_content_length: int = 500000):
        if EmailCleaner._initialized:
            return
            
        self.preserve_formatting = preserve_formatting
        self.remove_signatures = remove_signatures
        self.min_content_length = min_content_length
        self.max_content_length = max_content_length
        
        self._compile_patterns()
        self._setup_selectors()
        EmailCleaner._initialized = True
    
    def _compile_patterns(self):
        thread_patterns = [
            r'(?:on\s+.{1,200}?\s+(?:wrote|said|sent)|from:\s*.{1,200}?\s+to:|begin forwarded message)',
            r'-----+\s*original\s+message\s*-----+',
            r'_{10,}',
            r'------+\s*forwarded\s+message\s*------+',
            r'le\s+.{1,100}?\s+a\s+écrit\s*:',
            r'am\s+.{1,100}?\s+schrieb\s*.{0,50}?\s*:',
            r'el\s+.{1,100}?\s+escribió\s*:',
            r'в\s+.{1,100}?\s+написал\s*:',
            r'sent\s+from\s+(?:my\s+)?(?:iphone|ipad|android|mobile|blackberry)',
        ]
        self.thread_regex = re.compile('|'.join(f'(?:{p})' for p in thread_patterns), 
                                      re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        signature_patterns = [
            r'(?:best\s+regards?|sincerely|thanks?|cheers|regards?)\s*,?\s*$',
            r'sent\s+from\s+(?:outlook|my\s+(?:iphone|ipad|samsung|android))',
            r'get\s+outlook\s+for\s+.{1,50}',
            r'virus-free\s*\.?\s*www\.avg\.com',
            r'--\s*$',
            r'^\s*[-_=]{3,}\s*$',
            r'confidentiality|disclaimer|unsubscribe|legal notice',
        ]
        self.signature_regex = re.compile('|'.join(f'(?:{p})' for p in signature_patterns), 
                                         re.IGNORECASE | re.MULTILINE)
    
    def _setup_selectors(self):
        self.remove_elements = {
            'script', 'style', 'meta', 'link', 'title', 'head', 'noscript', 
            'iframe', 'object', 'embed', 'applet', 'form', 'input', 'button',
            'select', 'textarea', 'canvas', 'svg', 'audio', 'video'
        }
        
        self.remove_selectors = [
            '[style*="display:none"]', '[style*="visibility:hidden"]',
            '[style*="font-size:0"]', '[style*="height:0"]', '[style*="width:0"]',
            '[style*="opacity:0"]', '[style*="position:absolute"][style*="left:-"]',
            '.gmail_quote', '.gmail_signature', '.gmail_extra', '.gmail_default',
            '.gmail_attr', '.AppleMailSignature', '.outlook_signature', 
            '.yahoo_quoted', '.protonmail_quote', '.moz-cite-prefix',
            '.quoted-text', '.quote', '.reply', '.forward',
            '[class*="signature"]', '[id*="signature"]', '[class*="quote"]',
            '[id*="quote"]', '[class*="reply"]', '[id*="reply"]',
            'blockquote', 'cite', '.footer', '.header', '.tracking',
            '[class*="footer"]', '[class*="header"]', '[class*="tracking"]',
            '[class*="pixel"]', '[width="1"][height="1"]', 'img[width="0"]',
            'img[height="0"]', '.spacer', '[class*="spacer"]'
        ]
        
        self.whitespace_regex = re.compile(r'\s+')
        self.unicode_regex = re.compile(r'[\u200b-\u200d\ufeff]')
        self.email_regex = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        self.url_regex = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
    
    def clean(self, html_body: str) -> str:
        if not html_body or len(html_body.strip()) < 3:
            return ""
        
        if len(html_body) > self.max_content_length:
            html_body = html_body[:self.max_content_length]
        
        try:
            if not self._contains_html(html_body):
                return self._clean_plain_text(html_body)
            
            decoded_content = html.unescape(html_body)
            soup = BeautifulSoup(decoded_content, 'html.parser')
            
            self._remove_comments(soup)
            self._remove_unwanted_elements(soup)
            self._remove_hidden_content(soup)
            self._handle_email_artifacts(soup)
            
            text = self._extract_text(soup)
            text = self._normalize_text(text)
            text = self._remove_threads(text)
            
            if self.remove_signatures:
                text = self._remove_signatures_from_text(text)
            
            text = self._final_cleanup(text)
            
            return text if len(text) >= self.min_content_length else ""
            
        except Exception:
            return self._fallback_clean(html_body)
    
    def _contains_html(self, content: str) -> bool:
        return bool(re.search(r'<[^>]+>', content))
    
    def _clean_plain_text(self, text: str) -> str:
        text = self.unicode_regex.sub('', text)
        text = self.whitespace_regex.sub(' ', text)
        text = self._remove_threads(text)
        if self.remove_signatures:
            text = self._remove_signatures_from_text(text)
        return text.strip()
    
    def _remove_comments(self, soup: BeautifulSoup) -> None:
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
    
    def _remove_unwanted_elements(self, soup: BeautifulSoup) -> None:
        for tag_name in self.remove_elements:
            for tag in soup.find_all(tag_name):
                tag.decompose()
        
        for selector in self.remove_selectors:
            try:
                for element in soup.select(selector):
                    element.decompose()
            except:
                continue
    
    def _remove_hidden_content(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all(True):
            style = tag.get('style', '')
            if any(hidden in style.lower() for hidden in [
                'display:none', 'visibility:hidden', 'font-size:0px', 
                'height:0px', 'width:0px', 'opacity:0'
            ]):
                tag.decompose()
    
    def _handle_email_artifacts(self, soup: BeautifulSoup) -> None:
        for img in soup.find_all('img'):
            width = str(img.get('width', ''))
            height = str(img.get('height', ''))
            if (width in ['0', '1'] and height in ['0', '1']) or not img.get('alt', '').strip():
                img.decompose()
        
        for table in soup.find_all('table'):
            if not table.get_text(strip=True):
                table.decompose()
        
        for link in soup.find_all('a'):
            href = link.get('href', '')
            if 'unsubscribe' in href.lower() or 'tracking' in href.lower():
                link.decompose()
    
    def _extract_text(self, soup: BeautifulSoup) -> str:
        if self.preserve_formatting:
            for tag in soup.find_all(['p', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']):
                if tag.name == 'br':
                    tag.replace_with('\n')
                elif tag.name == 'li':
                    tag.insert(0, '• ')
                    tag.insert_after('\n')
                else:
                    tag.insert_after('\n')
            return soup.get_text()
        else:
            return soup.get_text(separator=' ', strip=True)
    
    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""
        
        text = unicodedata.normalize('NFKC', text)
        text = self.unicode_regex.sub('', text)
        text = text.replace('\xa0', ' ').replace('\u2000', ' ').replace('\u2001', ' ')
        text = text.replace('\u2002', ' ').replace('\u2003', ' ').replace('\u2009', ' ')
        
        if self.preserve_formatting:
            text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
            text = re.sub(r'[ \t]+', ' ', text)
        else:
            text = self.whitespace_regex.sub(' ', text)
        
        text = re.sub(r'([.!?])\1{2,}', r'\1', text)
        return text.strip()
    
    def _remove_threads(self, text: str) -> str:
        match = self.thread_regex.search(text)
        if match:
            text = text[:match.start()].strip()
        return text
    
    def _remove_signatures_from_text(self, text: str) -> str:
        lines = text.split('\n') if self.preserve_formatting else [text]
        
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if not line:
                continue
                
            if line == '--' or self.signature_regex.search(line):
                lines = lines[:i]
                break
            
            if i < len(lines) - 3 and len(line) < 50:
                next_lines = ' '.join(lines[i:i+3]).strip()
                if self.signature_regex.search(next_lines):
                    lines = lines[:i]
                    break
        
        return '\n'.join(lines) if self.preserve_formatting else ' '.join(lines)
    
    def _final_cleanup(self, text: str) -> str:
        if not text:
            return ""
        
        if self.preserve_formatting:
            text = re.sub(r'\n\s*\n+', '\n\n', text)
            text = re.sub(r'^\s+|\s+$', '', text, flags=re.MULTILINE)
        else:
            text = self.whitespace_regex.sub(' ', text)
        
        text = re.sub(r'^[^\w\s]*|[^\w\s]*$', '', text)
        return text.strip()
    
    def _fallback_clean(self, content: str) -> str:
        try:
            text = re.sub(r'<[^>]+>', '', content)
            text = html.unescape(text)
            text = self.whitespace_regex.sub(' ', text)
            return text.strip()
        except:
            return content.strip()

    def clean_email(html_body: str, preserve_formatting: bool = False, remove_signatures: bool = True) -> str:
        cleaner = EmailCleaner(preserve_formatting=preserve_formatting, remove_signatures=remove_signatures)
        return cleaner.clean(html_body)

    def clean_emails_batch(html_bodies: List[str], **kwargs) -> List[str]:
        cleaner = EmailCleaner(**kwargs)
        return [cleaner.clean(body) for body in html_bodies]