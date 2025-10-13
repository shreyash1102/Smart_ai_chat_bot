#  E-Commerce AI Chatbot with AWS Bedrock

A serverless customer support chatbot for e-commerce platforms using AWS services. Handles order tracking, returns, refunds, and product questions with AI-powered responses.

---

##  Overview

**Features:**
- Instant AI responses using Amazon Bedrock Nova Pro
- Conversation context across multiple messages
- Automatic FAQ learning from interactions
- Smart escalation to human agents
- Pre-configured e-commerce policies

**Note:** Backend-only implementation. No frontend included.

---

##  Architecture

```
Client (Postman) → API Gateway → Lambda → Bedrock/DynamoDB
```

**Flow:**
1. Client sends HTTP request to API Gateway
2. API Gateway routes to Lambda function
3. Lambda checks FAQ database, retrieves history, calls Bedrock AI
4. Saves messages/FAQs to DynamoDB
5. Returns response to client

---

## 🛠️ AWS Services

| Service | Purpose |
|---------|---------|
| **Lambda** | Core business logic (Python 3.12, 256MB, 30s timeout) |
| **API Gateway** | REST API endpoints |
| **DynamoDB** | Two tables: FAQTable & ChatSessions |
| **Bedrock** | AI model (amazon.nova-pro-v1:0) |
| **CloudWatch** | Logging and monitoring |
| **IAM** | Permissions management |

---

##  Database Schema

### FAQTable
| Field | Type | Description |
|-------|------|-------------|
| `faq_id` | String (PK) | Unique identifier |
| `question` | String | Customer question |
| `answer` | String | AI-generated answer |
| `created_at` | String | ISO timestamp |

### ChatSessions
| Field | Type | Description |
|-------|------|-------------|
| `session_id` | String (PK) | Session identifier |
| `message_ts` | String (SK) | ISO timestamp |
| `message_id` | String | Unique message ID |
| `user_id` | String | User identifier |
| `role` | String | "user" or "assistant" |
| `text` | String | Message content |
| `source` | String | "faq" or "model" |
| `escalate` | Boolean | Escalation flag |

---

##  API Endpoints

**Base URL:** `https://vwgmpblxoa.execute-api.us-east-1.amazonaws.com/prod`

### POST /chat
Send a message to the chatbot.

**Request:**
```json
{
  "user_id": "demo-user-2025",
  "message": "How do I track my order?",
  "session_id": "sess-abc123" // optional
}
```

**Response:**
```json
{
  "session_id": "sess-abc123def456",
  "message_id": "msg-xyz789",
  "reply": "You can track your order from your account...",
  "timestamp": "2025-10-13T15:39:06Z",
  "source": "model",
  "escalate": false
}
```

### GET /session/{session_id}
Retrieve conversation history.

**Response:**
```json
{
  "session_id": "sess-abc123",
  "messages": [
    {
      "message_id": "msg-001",
      "role": "user",
      "text": "How do I track my order?",
      "message_ts": "2025-10-13T15:40:00Z"
    },
    {
      "message_id": "msg-002",
      "role": "assistant",
      "text": "You can track your order...",
      "message_ts": "2025-10-13T15:40:01Z"
    }
  ],
  "message_count": 2
}
```

---

## 🚀 Setup Guide

### Prerequisites
- AWS Account
- AWS CLI configured
- Python 3.12
- Postman or cURL

### Step 1: Create DynamoDB Tables

```bash
# FAQTable
aws dynamodb create-table \
  --table-name FAQTable \
  --attribute-definitions AttributeName=faq_id,AttributeType=S \
  --key-schema AttributeName=faq_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1

# ChatSessions
aws dynamodb create-table \
  --table-name ChatSessions \
  --attribute-definitions \
    AttributeName=session_id,AttributeType=S \
    AttributeName=message_ts,AttributeType=S \
  --key-schema \
    AttributeName=session_id,KeyType=HASH \
    AttributeName=message_ts,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### Step 2: Create IAM Role

Create role with these permissions:
- `AWSLambdaBasicExecutionRole`
- DynamoDB read/write on FAQTable and ChatSessions
- Bedrock InvokeModel on amazon.nova-pro-v1:0

**Custom Policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:*:table/FAQTable",
        "arn:aws:dynamodb:us-east-1:*:table/ChatSessions"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0"
    }
  ]
}
```

### Step 3: Create Lambda Function

1. AWS Lambda Console → Create Function
2. Function name: `Sales_chat_bot`
3. Runtime: Python 3.12
4. Use IAM role from Step 2
5. Copy Lambda code
6. Set environment variables:
   - `FAQ_TABLE`: FAQTable
   - `SESSIONS_TABLE`: ChatSessions
   - `BEDROCK_MODEL_ID`: amazon.nova-pro-v1:0
   - `MAX_HISTORY_MESSAGES`: 10
7. Timeout: 30 seconds, Memory: 256 MB
8. Deploy

### Step 4: Create API Gateway

1. Create REST API: `chat-bot-sales-api`
2. Create resource `/chat` with POST method
3. Create resource `/session/{session_id}` with GET method
4. Integration: Lambda Proxy
5. Enable CORS on both resources
6. Deploy to `prod` stage
7. Copy Invoke URL

### Step 5: Enable Bedrock Access

1. Bedrock Console → Model access
2. Enable **Amazon Nova Pro**
3. Wait for "Access granted" status

---

##  Testing

### Test 1: New Conversation
```bash
curl -X POST https://vwgmpblxoa.execute-api.us-east-1.amazonaws.com/prod/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo-user",
    "message": "How do I track my order?"
  }'
```

### Test 2: Continue Conversation
```bash
curl -X POST https://vwgmpblxoa.execute-api.us-east-1.amazonaws.com/prod/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo-user",
    "session_id": "sess-abc123",
    "message": "What is your refund policy?"
  }'
```

### Test 3: Get History
```bash
curl https://vwgmpblxoa.execute-api.us-east-1.amazonaws.com/prod/session/sess-abc123
```

---

##  Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FAQ_TABLE` | FAQTable | FAQ table name |
| `SESSIONS_TABLE` | ChatSessions | Sessions table name |
| `BEDROCK_MODEL_ID` | amazon.nova-pro-v1:0 | AI model ID |
| `MAX_HISTORY_MESSAGES` | 10 | Context window size |

### Pre-configured Policies

- Returns: 30 days (15 for electronics)
- Free shipping: Orders over $50
- Standard shipping: $5.99 (5-7 days)
- Express shipping: $9.99 (2-3 days)
- Refunds: 5-10 business days

### Escalation Triggers

Auto-escalates for:
- Customer frustration
- Security concerns
- Complex disputes
- Payment issues
- Damaged items

---

##  Use Cases

**Supported queries:**
- Order tracking and status
- Return and refund policies
- Shipping inquiries
- Account management
- Product questions
- Order issues

---

##  Monitoring

**CloudWatch Logs:** `/aws/lambda/Sales_chat_bot`

**Key Metrics:**
- Invocations
- Duration (target < 2s)
- Errors (target < 1%)
- DynamoDB capacity
- Bedrock token usage

---

##  Limitations

- No frontend interface
- No authentication
- Single AI model
- Basic FAQ matching
- No analytics dashboard
- English only

---

## Future Enhancements

- [ ] API authentication
- [ ] Semantic FAQ search
- [ ] Multi-language support
- [ ] Web frontend
- [ ] Analytics dashboard
- [ ] CRM integration

---

##  Cost Estimate

**Monthly (10,000 requests):**
- Lambda: $0.20
- API Gateway: $0.04
- DynamoDB: $0.25
- Bedrock: $6.00
- CloudWatch: $0.50
- **Total: ~$7/month**

---

##  Resources

- [Lambda Guide](https://docs.aws.amazon.com/lambda/)
- [DynamoDB Guide](https://docs.aws.amazon.com/dynamodb/)
- [Bedrock Guide](https://docs.aws.amazon.com/bedrock/)
- [API Gateway Docs](https://docs.aws.amazon.com/apigateway/)

---

**Built with AWS Serverless Technologies**
