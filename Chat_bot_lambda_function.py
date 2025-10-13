import os
import json
import uuid
import datetime
import logging
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

FAQ_TABLE = os.environ.get("FAQ_TABLE", "FAQTable")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "ChatSessions")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
MAX_HISTORY_MESSAGES = int(os.environ.get("MAX_HISTORY_MESSAGES", "10"))
FAQ_MATCH_THRESHOLD = float(os.environ.get("FAQ_MATCH_THRESHOLD", "0.5"))


dynamodb = boto3.resource("dynamodb")
faq_table = dynamodb.Table(FAQ_TABLE)
sessions_table = dynamodb.Table(SESSIONS_TABLE)
bedrock = boto3.client("bedrock-runtime")


SYSTEM_PROMPT = (
    "You are a helpful, friendly customer support assistant for our Amazon-style e-commerce marketplace. "
    "Your role is to assist customers with orders, shipping, returns, refunds, product questions, and account issues.\n\n"
    
    "KEY POLICIES:\n"
    "- Returns: 30 days from purchase for most items (electronics 15 days)\n"
    "- Free shipping on orders over $50; otherwise $5.99\n"
    "- Refunds processed within 5-10 business days after return received\n"
    "- Standard shipping: 5-7 business days | Express: 2-3 business days\n"
    "- Warranty: 1 year manufacturer warranty on electronics\n"
    "- Damaged/defective items replaced at no cost\n\n"
    
    "COMMUNICATION STYLE:\n"
    "- Be warm, professional, and efficient\n"
    "- Keep responses under 150 words\n"
    "- Use conversational tone but stay professional\n"
    "- Acknowledge customer frustration if present\n"
    "- Provide specific information (order numbers, dates, amounts)\n\n"
    
    "WHEN TO ESCALATE:\n"
    "- Customer is very upset or frustrated\n"
    "- Complex refund disputes or damaged items requiring proof\n"
    "- Security concerns (account hacked, fraud)\n"
    "- Payment authorization issues\n"
    "- Requests for exceptions to standard policies\n"
    "- Technical issues you cannot resolve\n\n"
    
    "Use conversation history for context. If you cannot help, clearly state why and offer escalation to our support team."
)

SEED_FAQS = [
    {
        "question": "How do I track my order?",
        "answer": "You can track your order anytime from your account under 'Orders & Returns'. You'll get real-time updates via email at each stage: confirmed, shipped, and delivered. Most orders arrive within 5-7 business days with standard shipping."
    },
    {
        "question": "What is your return policy?",
        "answer": "We offer 30-day returns on most items from the date of purchase. Electronics have a 15-day return window. Items must be unused, in original packaging, and in resellable condition. Refunds are processed within 5-10 business days after we receive your return."
    },
    {
        "question": "How long does shipping take?",
        "answer": "Standard shipping takes 5-7 business days. Express shipping (2-3 business days) is available for $9.99. Free shipping applies to orders over $50 with standard shipping. Shipping times exclude weekends and holidays."
    },
    {
        "question": "Do you offer free shipping?",
        "answer": "Yes! Orders totaling $50 or more qualify for free standard shipping (5-7 business days). Orders under $50 have a $5.99 shipping fee. Express shipping is always $9.99, regardless of order total."
    },
    {
        "question": "How do I initiate a return?",
        "answer": "Go to 'Orders & Returns' in your account, select the item, and choose a return reason. Print the prepaid return label and ship it back to us. Once we receive and inspect your return, we'll process your refund within 5-10 business days."
    },
    {
        "question": "How long does a refund take?",
        "answer": "Refunds are processed within 5-10 business days after we receive and inspect your returned item. The time for the refund to appear in your account may vary depending on your bank (typically 3-5 additional business days)."
    },
    {
        "question": "What if my item is damaged or defective?",
        "answer": "We're sorry! Please contact us immediately with photos of the damage. We'll either send you a replacement at no cost or process a full refund. For most items, we can have a replacement shipped within 2-3 business days."
    },
    {
        "question": "Can I change or cancel my order?",
        "answer": "If your order hasn't shipped yet, you can cancel it from your account. Once it ships, you'll need to initiate a return. Contact our support team if you need to change the shipping address—we can sometimes update it before it ships."
    },
    {
        "question": "Do you have a warranty on electronics?",
        "answer": "Yes! All electronics come with a 1-year manufacturer warranty covering defects. This covers hardware failures but not accidental damage. To file a warranty claim, contact our support team with your order number and photos of the issue."
    },
    {
        "question": "What payment methods do you accept?",
        "answer": "We accept all major credit cards (Visa, MasterCard, American Express), debit cards, PayPal, Apple Pay, and Google Pay. Payment information is encrypted and secure. If you have issues during checkout, our support team can help troubleshoot."
    },
    {
        "question": "Is my personal information safe?",
        "answer": "Absolutely. We use bank-level encryption for all transactions and never share your information with third parties. Your data is secure whether shopping on our website or app. If you have security concerns, contact our support team immediately."
    },
    {
        "question": "How do I create an account?",
        "answer": "Click 'Sign Up' at the top of the page or in the app. Enter your email and create a password. You can optionally add your shipping and billing addresses. Create an account to save favorites, track orders, and get personalized recommendations."
    },
    {
        "question": "I forgot my password. What do I do?",
        "answer": "Click 'Forgot Password?' on the login page. Enter your email address, and we'll send you a reset link. Check your spam folder if you don't see it within a few minutes. If you continue having issues, our support team can help verify your identity and reset it."
    },
    {
        "question": "Can I change my shipping address after ordering?",
        "answer": "If your order hasn't shipped yet, you can often change the address from your account. Once it ships, the address cannot be changed. If you need help, contact us immediately with your order number—we may be able to update it in time."
    },
    {
        "question": "Why was my order delayed?",
        "answer": "Delays can occur due to payment verification, inventory updates, or carrier issues. You'll receive an email notification if there's any delay. You can check your order status anytime in your account. For extended delays, contact our support team—we may offer a discount or refund."
    },
    {
        "question": "Do you have a loyalty or rewards program?",
        "answer": "Yes! Members earn 1 point per $1 spent, redeemable for discounts. Sign up for free in your account settings. Plus, you'll get exclusive early access to sales and special member-only deals. Membership benefits include faster shipping on select items."
    },
    {
        "question": "How do I use a discount code?",
        "answer": "Enter your code in the 'Discount Code' field during checkout, before payment. The discount will apply to eligible items. Some codes may have restrictions (minimum purchase, specific categories, or new customers only). If your code doesn't work, contact us with the code details."
    },
    {
        "question": "What should I do if I was charged twice?",
        "answer": "Double charges are rare but can happen due to system issues. Check your account transactions to confirm. If you were genuinely charged twice, contact our support team immediately with your order numbers. We'll investigate and issue a refund if needed within 2-3 business days."
    },
    {
        "question": "Can I purchase as a guest without an account?",
        "answer": "Yes, guest checkout is available. However, creating an account gives you many benefits: order tracking, saved addresses, favorites, and access to your order history. Creating an account takes just 30 seconds and makes future shopping faster."
    },
    {
        "question": "What if an item is out of stock?",
        "answer": "Out-of-stock items will show as unavailable at checkout. You can add items to your Wishlist to be notified when they're back in stock. For high-demand items, stock can change quickly. Check back soon or contact us if you need help finding a similar alternative."
    }
]

def now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def create_session_id() -> str:
    """Generate a unique session ID."""
    return "sess-" + uuid.uuid4().hex[:12]

def save_message(session_id: str, message_id: str, user_id: str, role: str, text: str, extra: Optional[Dict] = None):
    """Save a message to the ChatSessions table."""
    item = {
        "session_id": session_id,
        "message_ts": now_iso(),
        "message_id": message_id,
        "user_id": user_id,
        "role": role,
        "text": text
    }
    if extra:
        item.update(extra)
    try:
        sessions_table.put_item(Item=item)
        logger.info(f"Saved message {message_id} to session {session_id}")
    except ClientError as e:
        logger.error(f"Failed to save message to ChatSessions: {e}")
        raise

def get_recent_history(session_id: str, limit: int = MAX_HISTORY_MESSAGES) -> List[Dict[str, Any]]:
    """Retrieve recent conversation history for a session."""
    try:
        resp = sessions_table.query(
            KeyConditionExpression=Key("session_id").eq(session_id),
            ScanIndexForward=False,
            Limit=limit
        )
        items = resp.get("Items", [])
        return sorted(items, key=lambda x: x["message_ts"])
    except ClientError as e:
        logger.error(f"Failed to query ChatSessions: {e}")
        return []

def similarity_score(s1: str, s2: str) -> float:
    """Calculate similarity between two strings using SequenceMatcher."""
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

def quick_faq_lookup(user_text: str) -> Optional[Dict[str, Any]]:
    """Search FAQ table for a matching question."""
    try:
        resp = faq_table.scan()
        faqs = resp.get("Items", [])
        logger.info(f"FAQ lookup: scanned {len(faqs)} FAQs")
    except ClientError as e:
        logger.error(f"Failed to scan FAQ table: {e}")
        return None

    if not faqs:
        logger.info("No FAQs found in table yet")
        return None

    best = None
    best_score = 0.0
    
    for faq in faqs:
        question = faq.get("question", "")
        answer = faq.get("answer", "")
        
        
        score = similarity_score(user_text, question)
        
        logger.debug(f"FAQ match - Q: '{question}' | Score: {score:.2f}")
        
        if score > best_score:
            best_score = score
            best = {
                "faq_id": faq.get("faq_id"),
                "question": question,
                "answer": answer,
                "score": score
            }
    
    if best and best["score"] >= FAQ_MATCH_THRESHOLD:
        logger.info(f"FAQ match found: {best['faq_id']} with score {best['score']:.2f}")
        return best
    
    logger.info(f"No FAQ match found (best score: {best_score:.2f})")
    return None

def save_new_faq(question: str, answer: str = "") -> str:
    """Save a new FAQ entry dynamically for future reuse."""
    faq_id = "faq-" + uuid.uuid4().hex[:12]
    item = {
        "faq_id": faq_id,
        "question": question,
        "answer": answer,
        "created_at": now_iso()
    }
    try:
        faq_table.put_item(Item=item)
        logger.info(f"Saved new FAQ {faq_id}: '{question}'")
        return faq_id
    except ClientError as e:
        logger.error(f"Failed to save new FAQ: {e}")
        return ""

def init_seed_faqs():
    """Initialize FAQ table with seed data on first run (optional)."""
    try:
        resp = faq_table.scan()
        count = resp.get("Count", 0)
        if count == 0:
            logger.info(f"FAQ table empty, seeding with {len(SEED_FAQS)} sample FAQs")
            for faq in SEED_FAQS:
                save_new_faq(faq["question"], faq["answer"])
    except Exception as e:
        logger.warning(f"Could not seed FAQs: {e}")

def build_prompt_text(system_prompt: str, history_items: List[Dict[str, Any]], user_message: str) -> str:
    """Build a prompt string from system prompt, history, and user message."""
    parts = [f"SYSTEM:\n{system_prompt.strip()}\n"]
    
    for item in history_items:
        role = item.get("role", "user").upper()
        content = item.get("text", "")
        parts.append(f"{role}:\n{content}\n")
    
    parts.append(f"USER:\n{user_message}\n")
    parts.append("ASSISTANT:")
    
    return "\n".join(parts)

def call_bedrock_model(prompt_text: str, max_tokens: int = 512) -> str:
    """Call Bedrock model and return generated text."""
    try:
        
        if "nova" in BEDROCK_MODEL_ID.lower():
            
            payload = {
                "schemaVersion": "messages-v1",
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt_text}]
                    }
                ],
                "inferenceConfig": {
                    "max_new_tokens": max_tokens,
                    "temperature": 0.7
                }
            }
        elif "llama" in BEDROCK_MODEL_ID.lower():
          
            payload = {
                "prompt": prompt_text,
                "max_gen_len": max_tokens,
                "temperature": 0.7,
                "top_p": 0.9
            }
        elif "mistral" in BEDROCK_MODEL_ID.lower():
            
            payload = {
                "prompt": prompt_text,
                "max_tokens": max_tokens,
                "temperature": 0.7,
                "top_p": 0.9
            }
        else:
          
            payload = {
                "inputText": prompt_text,
                "textGenerationConfig": {
                    "maxTokenCount": max_tokens,
                    "temperature": 0.7,
                    "topP": 0.9
                }
            }
        
        logger.info(f"Calling Bedrock model: {BEDROCK_MODEL_ID}")
        logger.debug(f"Payload: {json.dumps(payload, default=str)[:300]}")
        
        resp = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(payload).encode("utf-8")
        )
        
        body_bytes = resp.get("body").read()
        body_json = json.loads(body_bytes.decode("utf-8"))
        
        logger.debug(f"Bedrock response: {json.dumps(body_json, default=str)[:500]}")
        
        
        if "nova" in BEDROCK_MODEL_ID.lower():
            
            output = body_json.get("output", {})
            if "message" in output:
                message = output["message"]
                if "content" in message and isinstance(message["content"], list):
                    for content_block in message["content"]:
                        if isinstance(content_block, dict) and "text" in content_block:
                            return content_block["text"].strip()
            
            if "content" in body_json and isinstance(body_json["content"], list):
                for content_block in body_json["content"]:
                    if isinstance(content_block, dict) and "text" in content_block:
                        return content_block["text"].strip()
        elif "llama" in BEDROCK_MODEL_ID.lower():
            
            if "generation" in body_json and isinstance(body_json["generation"], str):
                return body_json["generation"].strip()
        elif "mistral" in BEDROCK_MODEL_ID.lower():
            
            if "outputs" in body_json and isinstance(body_json["outputs"], list):
                if len(body_json["outputs"]) > 0 and "text" in body_json["outputs"][0]:
                    return body_json["outputs"][0]["text"].strip()
        else:
            
            if "results" in body_json and isinstance(body_json["results"], list):
                if len(body_json["results"]) > 0 and "outputText" in body_json["results"][0]:
                    return body_json["results"][0]["outputText"].strip()
        
        
        for key in ("text", "generatedText", "generation", "output", "outputText"):
            if key in body_json and isinstance(body_json[key], str):
                return body_json[key].strip()
        
        logger.warning(f"Unexpected Bedrock response format: {body_json}")
        return "I encountered an unexpected response format. Please try again or contact support."
        
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        logger.error(f"Bedrock API error ({error_code}): {error_msg}")
        
        if "ValidationException" in error_code or "InvalidParameterException" in error_code:
            return "The AI model configuration needs adjustment. Please contact support."
        elif "ThrottlingException" in error_code or "ServiceQuotaExceededException" in error_code:
            return "The service is temporarily busy. Please try again in a moment."
        elif "ModelNotFound" in error_code or "AccessDenied" in error_code:
            return "The requested model is not available. Please contact support."
        else:
            return f"AI service error: {error_msg}. Please try again or contact support."
    except Exception as e:
        logger.error(f"Unexpected error calling Bedrock: {type(e).__name__}: {e}")
        return "An unexpected error occurred. Please contact support."

def should_escalate(text: str) -> bool:
    """Check if response indicates need for human escalation."""
    escalation_triggers = [
        "escalate", "speak to human", "contact support", "human agent",
        "contact us", "need assistance", "supervisor", "manager",
        "security concern", "fraud", "hacked", "suspicious",
        "refund dispute", "damaged", "defective", "exception",
        "very upset", "angry", "frustrated"
    ]
    text_lower = text.lower()
    return any(trigger in text_lower for trigger in escalation_triggers)

def build_response(status_code: int, payload: Dict[str, Any]):
    """Build Lambda response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Requested-With",
            "Access-Control-Allow-Methods": "OPTIONS,POST,GET"
        },
        "body": json.dumps(payload)
    }

def lambda_handler(event, context):
    """Main Lambda handler for chat requests."""
    logger.info(f"Received event: {json.dumps(event)}")
    
    
    init_seed_faqs()
    
    
    if event.get("httpMethod") == "OPTIONS":
        return build_response(200, {"message": "CORS preflight OK"})

    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return build_response(400, {"error": "Invalid JSON body"})

    user_id = body.get("user_id", "").strip()
    user_message = body.get("message", "").strip()
    session_id = body.get("session_id") or create_session_id()

    if not user_id or not user_message:
        return build_response(400, {"error": "user_id and message are required"})

    logger.info(f"Processing message from user {user_id} in session {session_id}")

    
    user_msg_id = "msg-" + uuid.uuid4().hex[:12]
    save_message(session_id, user_msg_id, user_id, "user", user_message)

    
    history = get_recent_history(session_id, limit=MAX_HISTORY_MESSAGES)
    logger.info(f"Retrieved {len(history)} messages from history")

    
    faq_hit = None 
    
    if faq_hit:
        reply_text = faq_hit["answer"]
        source = "faq"
        escalate = False
        logger.info(f"Using FAQ response: {faq_hit['faq_id']}")
    else:
        
        save_new_faq(user_message)
        
        
        prompt_text = build_prompt_text(SYSTEM_PROMPT, history, user_message)
        reply_text = call_bedrock_model(prompt_text, max_tokens=300)
        source = "model"
        escalate = should_escalate(reply_text)
        
        
        save_new_faq(user_message, answer=reply_text)
        logger.info(f"Generated response via model (escalate={escalate})")

    
    assistant_msg_id = "msg-" + uuid.uuid4().hex[:12]
    save_message(
        session_id, 
        assistant_msg_id, 
        user_id, 
        "assistant", 
        reply_text, 
        extra={"source": source, "escalate": escalate}
    )

    resp_payload = {
        "session_id": session_id,
        "message_id": assistant_msg_id,
        "reply": reply_text,
        "timestamp": now_iso(),
        "source": source,
        "escalate": escalate
    }

    logger.info(f"Returning response: source={source}, escalate={escalate}")
    return build_response(200, resp_payload)
