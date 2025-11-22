# Deploying Production AI Agents: Lessons from Building Workflow Automation at Scale

**Author:** Tony V. Nguyen
**Date:** November 2025
**Reading Time:** 15 minutes
**Tags:** #AI #MachineLearning #GenAI #ProductionML #Automation

---

## The Challenge: Automating Manufacturing Operations with AI

When I joined Wiko Cutlery as Lead Software Engineer, we were managing operations across three manufacturing facilities in Hong Kong. The coordination overhead was massive:

- **35% of staff time** spent on manual coordination
- **Production schedules** updated manually across facilities
- **Inventory management** done via spreadsheets and phone calls
- **Quality control data** siloed in different systems

The opportunity was clear: automate operational workflows using AI.

The result? We built an AI agent that:
- ✅ Reduced manual coordination overhead **35%**
- ✅ Increased production capacity **40%**
- ✅ Automated cross-facility communication
- ✅ Processed 1000+ operational decisions per day

This is the story of how we built, deployed, and maintained a production AI system in a traditional manufacturing environment.

## Part 1: Choosing the Right AI Stack

### The Requirements

Before choosing technology, we defined our needs:

**Functional Requirements:**
1. Natural language understanding (process messages in Chinese and English)
2. Decision-making capabilities (scheduling, resource allocation)
3. Integration with existing systems (ERP, WeCom, databases)
4. Real-time responses (< 3 seconds)
5. Multi-facility coordination

**Non-Functional Requirements:**
1. **Cost-effective:** Can't spend $10K/month on API calls
2. **Reliable:** Manufacturing can't stop for API downtime
3. **Auditable:** Need logs of all decisions
4. **Privacy-compliant:** Manufacturing data stays on-premise where possible

### Evaluating LLM Options (Late 2024)

| Model | Pros | Cons | Cost (1M tokens) |
|-------|------|------|------------------|
| **GPT-4** | Excellent reasoning, English/Chinese support | Expensive, OpenAI dependency | $30-60 |
| **Claude 3** | Great at following instructions, good Chinese | Expensive, Anthropic dependency | $15-75 |
| **Llama 2 70B** | Open source, can self-host | Lower quality reasoning | Self-hosted compute |
| **Hunyuan T1** | Tencent's LLM, excellent Chinese, WeCom native | Primarily Chinese market | $5-10 |
| **DeepSeek** | Strong reasoning, cost-effective | Newer, less proven | $0.14-0.28 |

**Our Decision: Hybrid Approach**

We used a combination:
- **Hunyuan T1** for Chinese language tasks and WeCom integration
- **DeepSeek** for complex reasoning and cost-sensitive workloads
- **Rule-based systems** for deterministic tasks (don't use AI where rules suffice)

**Why Hybrid?**
- Hunyuan T1's native WeCom integration saved weeks of development
- DeepSeek's low cost allowed us to experiment liberally
- Fallback to rule-based systems ensured reliability

## Part 2: Architecture Design

### System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    WeCom (WeChat Work)                  │
│              Manufacturing Staff Interface              │
└────────────────────┬────────────────────────────────────┘
                     │ Messages
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  Message Router                         │
│         (Parse intent, route to appropriate LLM)       │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   ┌─────────┐  ┌─────────┐  ┌──────────┐
   │ Hunyuan │  │DeepSeek │  │  Rules   │
   │   T1    │  │   API   │  │  Engine  │
   └────┬────┘  └────┬────┘  └────┬─────┘
        │            │            │
        └────────────┼────────────┘
                     ▼
         ┌───────────────────────┐
         │   Action Executor     │
         │ (Database, ERP, APIs) │
         └───────────────────────┘
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
    ┌────────┐  ┌────────┐  ┌────────┐
    │Facility│  │Facility│  │Facility│
    │   A    │  │   B    │  │   C    │
    └────────┘  └────────┘  └────────┘
```

### Core Components

**1. Message Router (Intent Classification)**

```python
from typing import Tuple, Optional
import re

class MessageRouter:
    """
    Routes incoming messages to appropriate handler based on intent.
    """

    def __init__(self, hunyuan_client, deepseek_client):
        self.hunyuan = hunyuan_client
        self.deepseek = deepseek_client

        # Define intent patterns
        self.intent_patterns = {
            'production_schedule': [
                r'生产.*计划', r'schedule.*production',
                r'安排.*生产', r'plan.*manufacturing'
            ],
            'inventory_check': [
                r'库存', r'inventory', r'stock',
                r'剩余.*数量'
            ],
            'quality_issue': [
                r'质量.*问题', r'quality.*issue',
                r'defect', r'不良品'
            ],
            'coordination': [
                r'协调', r'coordinate', r'沟通'
            ]
        }

    def classify_intent(self, message: str) -> str:
        """
        Classify message intent using pattern matching first,
        fallback to LLM if uncertain.
        """
        # Try pattern matching (fast, cheap, deterministic)
        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    return intent

        # Fallback: Use LLM for classification
        return self._llm_classify(message)

    def _llm_classify(self, message: str) -> str:
        """Use LLM to classify ambiguous messages"""
        prompt = f"""
        Classify the following message into one of these categories:
        - production_schedule
        - inventory_check
        - quality_issue
        - coordination
        - other

        Message: {message}

        Respond with ONLY the category name.
        """

        response = self.hunyuan.complete(prompt, max_tokens=20)
        return response.strip().lower()

    def route(self, message: str) -> Tuple[str, callable]:
        """
        Route message to appropriate handler.

        Returns:
            Tuple of (intent, handler_function)
        """
        intent = self.classify_intent(message)

        handlers = {
            'production_schedule': self.handle_production_schedule,
            'inventory_check': self.handle_inventory_check,
            'quality_issue': self.handle_quality_issue,
            'coordination': self.handle_coordination,
        }

        handler = handlers.get(intent, self.handle_generic)
        return intent, handler

    def handle_production_schedule(self, message: str) -> dict:
        """Handle production scheduling requests"""
        # Use DeepSeek for complex reasoning
        return self._process_with_deepseek(message, 'production_schedule')

    def handle_inventory_check(self, message: str) -> dict:
        """Handle inventory queries"""
        # Use rules engine for simple inventory lookups
        return self._process_with_rules(message, 'inventory')

    def handle_quality_issue(self, message: str) -> dict:
        """Handle quality issues"""
        # Use Hunyuan for Chinese language processing
        return self._process_with_hunyuan(message, 'quality')

    def handle_coordination(self, message: str) -> dict:
        """Handle inter-facility coordination"""
        return self._process_with_hunyuan(message, 'coordination')
```

**2. LLM Wrapper with Retry Logic**

```python
import time
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class LLMClient:
    """
    Wrapper for LLM API calls with:
    - Retry logic
    - Error handling
    - Caching
    - Rate limiting
    - Cost tracking
    """

    def __init__(self, api_key: str, model: str, max_retries: int = 3):
        self.api_key = api_key
        self.model = model
        self.max_retries = max_retries
        self.cache = {}  # Simple in-memory cache

    def complete(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        cache_ttl: int = 300,
        **kwargs
    ) -> str:
        """
        Call LLM API with retry logic and caching.
        """
        # Check cache first
        cache_key = self._generate_cache_key(prompt, max_tokens, temperature)
        if cache_key in self.cache:
            cached_result, timestamp = self.cache[cache_key]
            if time.time() - timestamp < cache_ttl:
                logger.info(f"Cache hit for prompt: {prompt[:50]}...")
                return cached_result

        # Try API call with retries
        for attempt in range(self.max_retries):
            try:
                response = self._call_api(prompt, max_tokens, temperature, **kwargs)

                # Cache successful response
                self.cache[cache_key] = (response, time.time())

                # Log cost
                self._track_cost(prompt, response)

                return response

            except Exception as e:
                logger.warning(f"API call failed (attempt {attempt + 1}/{self.max_retries}): {e}")

                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All retries exhausted for prompt: {prompt[:50]}...")
                    raise

        raise Exception("Failed to get LLM response after all retries")

    def _call_api(self, prompt: str, max_tokens: int, temperature: float, **kwargs) -> str:
        """Make actual API call (implement based on specific LLM provider)"""
        # Implementation depends on LLM provider
        # For Hunyuan T1, DeepSeek, etc.
        pass

    def _generate_cache_key(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """Generate cache key from request parameters"""
        import hashlib
        key_string = f"{prompt}_{max_tokens}_{temperature}_{self.model}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def _track_cost(self, prompt: str, response: str):
        """Track API costs"""
        input_tokens = len(prompt) // 4  # Rough estimate
        output_tokens = len(response) // 4

        # Cost calculation based on model pricing
        cost_per_1m_input = 0.14  # DeepSeek pricing
        cost_per_1m_output = 0.28

        cost = (
            (input_tokens / 1_000_000) * cost_per_1m_input +
            (output_tokens / 1_000_000) * cost_per_1m_output
        )

        logger.info(f"API call cost: ${cost:.6f} ({input_tokens} in, {output_tokens} out)")
```

**3. Production Scheduler with AI**

```python
from datetime import datetime, timedelta
from typing import List, Dict
import pandas as pd

class ProductionScheduler:
    """
    AI-powered production scheduler that optimizes:
    - Resource allocation
    - Machine utilization
    - Cross-facility coordination
    - Delivery deadlines
    """

    def __init__(self, llm_client: LLMClient, db_connection):
        self.llm = llm_client
        self.db = db_connection

    def optimize_schedule(
        self,
        orders: List[Dict],
        facilities: List[Dict],
        constraints: Dict
    ) -> Dict:
        """
        Generate optimized production schedule using AI.
        """
        # Get current state
        current_schedules = self._get_current_schedules()
        machine_availability = self._get_machine_availability()
        inventory_levels = self._get_inventory_levels()

        # Build context for LLM
        context = self._build_scheduling_context(
            orders, facilities, current_schedules,
            machine_availability, inventory_levels, constraints
        )

        # Generate schedule with LLM
        schedule_prompt = f"""
        You are a production scheduler for a manufacturing facility.

        Current State:
        {context}

        New Orders:
        {self._format_orders(orders)}

        Constraints:
        - Each facility has {constraints['max_concurrent_jobs']} machines
        - Lead time must be minimized
        - Each job requires specific machine types
        - Delivery deadlines must be met

        Generate an optimized production schedule that:
        1. Assigns each order to a specific facility
        2. Specifies start and end times
        3. Minimizes total lead time
        4. Balances load across facilities

        Respond in JSON format:
        {{
            "schedule": [
                {{
                    "order_id": "...",
                    "facility": "...",
                    "machine": "...",
                    "start_time": "2024-11-25T09:00:00",
                    "end_time": "2024-11-25T17:00:00",
                    "reasoning": "..."
                }}
            ],
            "expected_completion": "2024-11-30",
            "utilization_rate": 0.85
        }}
        """

        response = self.llm.complete(
            schedule_prompt,
            max_tokens=2000,
            temperature=0.3  # Lower temperature for more deterministic scheduling
        )

        schedule = self._parse_schedule(response)

        # Validate schedule
        if not self._validate_schedule(schedule, constraints):
            logger.warning("LLM-generated schedule violates constraints, applying corrections...")
            schedule = self._correct_schedule(schedule, constraints)

        return schedule

    def _validate_schedule(self, schedule: Dict, constraints: Dict) -> bool:
        """
        Validate that LLM-generated schedule meets all constraints.

        This is CRITICAL—never trust LLM output for production decisions
        without validation.
        """
        for item in schedule['schedule']:
            # Check time validity
            start = datetime.fromisoformat(item['start_time'])
            end = datetime.fromisoformat(item['end_time'])

            if end <= start:
                logger.error(f"Invalid time range for order {item['order_id']}")
                return False

            # Check facility capacity
            facility_load = self._calculate_facility_load(
                item['facility'],
                start,
                end,
                schedule
            )

            if facility_load > constraints['max_concurrent_jobs']:
                logger.error(f"Facility {item['facility']} overloaded")
                return False

        return True

    def _build_scheduling_context(self, orders, facilities, current_schedules,
                                   machine_availability, inventory_levels, constraints):
        """Build comprehensive context string for LLM"""
        context_parts = []

        # Current schedules
        context_parts.append("Current Production Schedule:")
        for schedule in current_schedules:
            context_parts.append(
                f"- Order {schedule['order_id']}: "
                f"{schedule['facility']}, "
                f"{schedule['start_time']} to {schedule['end_time']}"
            )

        # Machine availability
        context_parts.append("\nMachine Availability:")
        for facility, machines in machine_availability.items():
            available = sum(1 for m in machines if m['status'] == 'available')
            context_parts.append(f"- {facility}: {available}/{len(machines)} machines available")

        # Inventory
        context_parts.append("\nInventory Levels:")
        for item, quantity in inventory_levels.items():
            context_parts.append(f"- {item}: {quantity} units")

        return "\n".join(context_parts)
```

## Part 3: Handling Edge Cases & Failures

### The Reality of Production AI

LLMs are probabilistic. They fail. They hallucinate. They produce garbage.

**Our Failure Modes:**

1. **Hallucinated Data:** LLM invents order IDs that don't exist
2. **Invalid JSON:** Response isn't parseable
3. **Constraint Violations:** Schedule exceeds facility capacity
4. **API Timeouts:** LLM takes > 30s to respond
5. **Cost Explosions:** Accidentally calling API 1000 times in a loop

### Defensive Programming Strategies

**1. Always Validate LLM Outputs**

```python
def safe_parse_json(text: str) -> Optional[dict]:
    """
    Safely parse JSON from LLM response.
    LLMs sometimes wrap JSON in markdown code blocks.
    """
    # Remove markdown code blocks
    text = re.sub(r'```json\n?', '', text)
    text = re.sub(r'```\n?', '', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        logger.error(f"Raw text: {text}")

        # Try to extract JSON from text
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass

        return None
```

**2. Implement Fallbacks**

```python
def get_production_schedule(order_id: str) -> Dict:
    """
    Get production schedule with multiple fallback strategies.
    """
    try:
        # Try AI-powered scheduling
        return ai_schedule(order_id)
    except APIError:
        logger.warning("AI scheduling failed, trying rule-based fallback...")
        return rule_based_schedule(order_id)
    except Exception as e:
        logger.error(f"All scheduling methods failed: {e}")
        return manual_scheduling_required(order_id)
```

**3. Rate Limiting**

```python
from functools import wraps
import time

class RateLimiter:
    """
    Simple token bucket rate limiter to prevent API abuse.
    """

    def __init__(self, max_calls_per_minute: int = 60):
        self.max_calls = max_calls_per_minute
        self.calls = []

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()

            # Remove calls older than 1 minute
            self.calls = [t for t in self.calls if now - t < 60]

            # Check if we've exceeded rate limit
            if len(self.calls) >= self.max_calls:
                wait_time = 60 - (now - self.calls[0])
                logger.warning(f"Rate limit reached, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
                self.calls = []

            # Record this call
            self.calls.append(now)

            return func(*args, **kwargs)

        return wrapper

# Usage
@RateLimiter(max_calls_per_minute=100)
def call_llm_api(prompt):
    return llm_client.complete(prompt)
```

## Part 4: Monitoring & Observability

### What We Monitor

**1. API Metrics:**
- Latency (p50, p95, p99)
- Error rates
- Cost per day
- Token usage

**2. Business Metrics:**
- Decisions automated per day
- Manual interventions required
- Accuracy of AI decisions
- Time saved

**3. Quality Metrics:**
- Constraint violation rate
- Schedule adherence
- User satisfaction scores

### Custom Monitoring Dashboard

```python
import prometheus_client as prom

# Define metrics
api_latency = prom.Histogram(
    'llm_api_latency_seconds',
    'LLM API call latency',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

api_errors = prom.Counter(
    'llm_api_errors_total',
    'Total LLM API errors',
    ['error_type']
)

api_cost = prom.Counter(
    'llm_api_cost_usd',
    'Total API cost in USD'
)

constraint_violations = prom.Counter(
    'schedule_constraint_violations_total',
    'Schedules that violated constraints'
)

# Instrument code
@api_latency.time()
def call_llm(prompt):
    try:
        response = llm_client.complete(prompt)
        api_cost.inc(calculate_cost(prompt, response))
        return response
    except Exception as e:
        api_errors.labels(error_type=type(e).__name__).inc()
        raise
```

### Alerting Rules

```yaml
# Prometheus alert rules
groups:
  - name: llm_api_alerts
    rules:
      - alert: HighLLMLatency
        expr: llm_api_latency_seconds{quantile="0.95"} > 5
        for: 5m
        annotations:
          summary: "LLM API latency is high"

      - alert: HighErrorRate
        expr: rate(llm_api_errors_total[5m]) > 0.1
        for: 2m
        annotations:
          summary: "LLM API error rate > 10%"

      - alert: DailyCostExceeded
        expr: increase(llm_api_cost_usd[24h]) > 100
        annotations:
          summary: "Daily API cost exceeded $100"
```

## Part 5: Cost Optimization

### The Cost Reality

**Initial costs (month 1):**
- 10,000 LLM API calls/day
- Average 500 tokens per request
- $0.28/1M tokens (DeepSeek)
- **Total:** $42/day = **$1,260/month**

**This was unsustainable.**

### Optimization Strategies

**1. Aggressive Caching**

```python
# Before: Every inventory check calls LLM
def check_inventory(item_id):
    prompt = f"What's the inventory level for {item_id}?"
    return llm.complete(prompt)

# After: Cache results, use rules engine
def check_inventory(item_id):
    # Just query the database!
    return db.query("SELECT quantity FROM inventory WHERE id = ?", item_id)
```

**Lesson:** Don't use AI where a simple database query suffices.

**2. Batch Processing**

```python
# Before: One API call per order
for order in orders:
    schedule = schedule_order(order)  # Separate API call

# After: Batch multiple orders
batch_prompt = f"""
Schedule these {len(orders)} orders:
{format_orders(orders)}
"""
schedule = llm.complete(batch_prompt)  # Single API call
```

**3. Prompt Compression**

```python
# Before: Verbose prompt (1500 tokens)
prompt = f"""
You are a helpful AI assistant for manufacturing operations.
Your task is to analyze the following production data and
provide recommendations...

Current State:
- Facility A has 10 machines, 7 are currently in use...
- Facility B has 8 machines, 5 are currently in use...
[much more verbose context]

Please analyze and provide recommendations.
"""

# After: Compressed prompt (400 tokens)
prompt = f"""
Production optimization task.

State:
- Facility A: 7/10 machines in use
- Facility B: 5/8 machines in use

Recommend: optimal job allocation
"""
```

**4. Model Selection Based on Task Complexity**

```python
def route_to_model(task_complexity: str, prompt: str):
    if task_complexity == 'simple':
        # Use cheaper model
        return deepseek_client.complete(prompt)  # $0.14/1M tokens
    elif task_complexity == 'complex':
        # Use more capable model
        return gpt4_client.complete(prompt)  # $30/1M tokens
    else:
        # Rule-based for trivial tasks
        return rule_engine.process(prompt)  # $0
```

### Results After Optimization

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Daily API Calls | 10,000 | 800 | 92% reduction |
| Avg Tokens/Call | 500 | 200 | 60% reduction |
| Daily Cost | $42 | $1.80 | 96% cheaper |
| **Monthly Cost** | **$1,260** | **$54** | **$1,206 saved** |

## Key Lessons Learned

### 1. **LLMs Aren't Magic—Use Them Strategically**

**Good LLM Use Cases:**
- Natural language understanding
- Complex reasoning
- Unstructured data processing

**Bad LLM Use Cases:**
- Simple lookups (use database)
- Deterministic logic (use code)
- Math calculations (use code)

### 2. **Always Validate AI Outputs**

Never trust LLM responses for production decisions without validation:
- Validate JSON structure
- Check constraint compliance
- Verify references exist (no hallucinated IDs)
- Implement sanity checks

### 3. **Cost Optimization is Critical**

Strategies that worked:
- ✅ Cache aggressively
- ✅ Batch requests
- ✅ Compress prompts
- ✅ Use cheaper models when possible
- ✅ Fallback to rules engines

### 4. **Monitoring == Production Readiness**

You need:
- Real-time latency metrics
- Error rate tracking
- Cost monitoring with alerts
- Business metric dashboards

### 5. **Start Small, Iterate**

Don't try to automate everything at once:
1. Pick ONE high-impact workflow
2. Build MVP in 2 weeks
3. Deploy and monitor closely
4. Iterate based on feedback
5. Expand to more workflows

## Final Thoughts

Building production AI systems is different from building demos. You need:
- **Robust error handling**
- **Comprehensive monitoring**
- **Cost optimization**
- **Validation layers**
- **Fallback strategies**

But when done right, the impact is real:
- 35% reduction in manual coordination
- 40% increase in production capacity
- 1000+ operational decisions automated daily

AI agents aren't replacing humans—they're augmenting our capabilities and eliminating repetitive work.

---

## Resources

**Code Examples:**
- [GitHub: Production AI Agent Framework](https://github.com/tonesgainz/production-ai-agents)

**Connect:**
- [LinkedIn](https://linkedin.com/in/tonenv)
- [Twitter](https://twitter.com/tonesgainz)
- Email: tony@snfactor.com

---

*Tony V. Nguyen is a DevOps Engineer at RevisionDojo (YC W24) and former Lead Software Engineer at Wiko Cutlery, where he built AI-powered manufacturing automation systems.*
