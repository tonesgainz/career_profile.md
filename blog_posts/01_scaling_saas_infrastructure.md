# Scaling SaaS Infrastructure to 220K+ Users: Lessons from Y Combinator W24

**Author:** Tony V. Nguyen
**Date:** November 2025
**Reading Time:** 12 minutes
**Tags:** #DevOps #SaaS #YCombinator #Infrastructure #Scalability

---

## Introduction

Six months ago, I joined RevisionDojo, one of the fastest-growing AI SaaS companies in Y Combinator's W24 batch. Our mission: help 220,000+ International Baccalaureate students across 180+ countries prepare for their exams using AI-powered learning tools.

When I started, we were serving about 10,000 users. By month three, we hit 100K. By month five, we crossed 200K. This 20x growth in infrastructure demand happened while we were a lean team shipping features daily.

This is the story of how we scaled—the technical decisions, the mistakes, the late-night incidents, and the lessons learned.

## The Starting Point

### Initial Architecture (10K users)

When I joined, our stack looked like this:

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Next.js   │────────▶│  Node.js API │────────▶│ PostgreSQL  │
│   Frontend  │         │   (Express)  │         │  (single)   │
└─────────────┘         └──────────────┘         └─────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │   OpenAI     │
                        │     API      │
                        └──────────────┘
```

**The Problems:**
- Single PostgreSQL instance (no read replicas)
- N+1 queries everywhere
- No caching layer
- API server bottlenecked at ~500 concurrent users
- Manual deployments
- Minimal monitoring

**The Reality Check:**

Our first major incident happened at 15K users. The database maxed out connections, API response times went from 200ms to 5 seconds, and users started complaining on Twitter. We were trending for the wrong reasons.

## Phase 1: Immediate Firefighting (10K → 50K users)

### Week 1: Database Optimization

**Problem:** PostgreSQL connection pool exhaustion

**Solution:** Immediate tactical fixes
```sql
-- Before: N+1 query nightmare
-- Loading user + their progress + their courses = 100+ queries per page

-- After: Strategic joins and batching
SELECT u.*, up.*, c.*
FROM users u
LEFT JOIN user_progress up ON u.id = up.user_id
LEFT JOIN courses c ON up.course_id = c.id
WHERE u.id = ANY($1::int[])
```

**Impact:**
- Query count: 100+ → 3 per page load
- Database load: Reduced 70%
- Response time: 5s → 800ms

**Key Lesson:** Profile your database queries FIRST. Most scaling issues start with inefficient data access.

### Week 2: Add Read Replicas

We couldn't afford downtime, so we used AWS RDS for easy replication setup:

```python
# Database router
class DatabaseRouter:
    def db_for_read(self, model, **hints):
        """Route read queries to replicas"""
        return random.choice(['replica_1', 'replica_2'])

    def db_for_write(self, model, **hints):
        """Route writes to primary"""
        return 'primary'
```

**Setup:**
- 1 primary (writes)
- 2 read replicas (reads)
- Connection pooling with pgbouncer

**Impact:**
- Read capacity: 3x increase
- Primary database CPU: 80% → 25%
- Can now handle 50K concurrent users

### Week 3: Implement Redis Caching

We added Redis for session management and frequently accessed data:

```python
import redis
from functools import wraps

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

def cache_result(ttl=300):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

            # Try cache first
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)

            # Execute function
            result = func(*args, **kwargs)

            # Store in cache
            redis_client.setex(cache_key, ttl, json.dumps(result))

            return result
        return wrapper
    return decorator

@cache_result(ttl=3600)
def get_course_content(course_id):
    # Expensive database query
    return db.query(Course).filter_by(id=course_id).first()
```

**Cached Data:**
- User sessions
- Course metadata
- Dashboard statistics
- API responses for common queries

**Impact:**
- Database queries reduced 40%
- Dashboard load time: 2s → 400ms
- Session lookup: 100ms → 5ms

## Phase 2: Architectural Changes (50K → 150K users)

### The Wake-Up Call

At 50K users, we had another incident. This time, the Node.js API server was the bottleneck. CPU usage spiked to 100%, and we started seeing 503 errors.

**Root Cause:** Single API server handling all requests

**The Realization:** We needed horizontal scaling.

### Containerization with Docker

First, we containerized everything:

```dockerfile
# Dockerfile for API server
FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./
RUN npm ci --production

# Copy source code
COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node healthcheck.js || exit 1

EXPOSE 8000

CMD ["node", "server.js"]
```

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  api:
    build: ./api
    deploy:
      replicas: 5
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
    ports:
      - "8000-8004:8000"

  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    ports:
      - "80:80"
    depends_on:
      - api

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  postgres:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  redis_data:
  postgres_data:
```

**Load Balancing with Nginx:**

```nginx
upstream api_servers {
    least_conn;
    server api:8000;
    server api:8001;
    server api:8002;
    server api:8003;
    server api:8004;
}

server {
    listen 80;

    location / {
        proxy_pass http://api_servers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /health {
        access_log off;
        return 200 "healthy\n";
    }
}
```

**Impact:**
- API capacity: 5x increase
- Fault tolerance: One server can fail without downtime
- Deploy strategy: Rolling updates with zero downtime

### Move to AWS (Managed Services)

Running everything on Docker Compose on a single EC2 instance wasn't sustainable. We migrated to AWS managed services:

**New Architecture:**

```
┌───────────────┐
│ CloudFront    │ ← CDN for static assets
│ (CDN)         │
└───────┬───────┘
        │
┌───────▼───────────────────────────────┐
│ Application Load Balancer             │
└───────┬────────────┬──────────────────┘
        │            │
    ┌───▼────┐   ┌───▼────┐
    │  ECS   │   │  ECS   │  ← Fargate containers
    │ Task 1 │   │ Task 2 │     (auto-scaling)
    └───┬────┘   └───┬────┘
        │            │
    ┌───▼────────────▼────┐
    │ ElastiCache (Redis) │
    └───┬─────────────────┘
        │
    ┌───▼──────────────────────┐
    │ RDS PostgreSQL           │
    │ (Multi-AZ with replicas) │
    └──────────────────────────┘
```

**Key AWS Services:**
- **ECS Fargate:** Managed containers (no server management)
- **Application Load Balancer:** Distributes traffic, health checks
- **RDS:** Managed PostgreSQL with automatic backups and multi-AZ
- **ElastiCache:** Managed Redis cluster
- **CloudFront:** CDN for static assets (reduced latency globally)
- **CloudWatch:** Monitoring and alerting

**Infrastructure as Code (Terraform):**

```hcl
# ecs_service.tf
resource "aws_ecs_service" "api" {
  name            = "api-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 5

  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  # Auto-scaling based on CPU
  lifecycle {
    ignore_changes = [desired_count]
  }
}

# Auto-scaling policy
resource "aws_appautoscaling_target" "api_scaling" {
  max_capacity       = 20
  min_capacity       = 5
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "api-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api_scaling.resource_id
  scalable_dimension = aws_appautoscaling_target.api_scaling.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api_scaling.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 70.0
  }
}
```

**Benefits:**
- **Managed services:** No server patching, backups automated
- **Multi-AZ:** High availability across availability zones
- **Auto-scaling:** Automatically scale containers based on traffic
- **Global performance:** CloudFront CDN reduced latency 60% for international users

**Cost:**
- Before: $500/month (single EC2 instance)
- After: $2,000/month (but serving 10x users)
- **Unit economics:** Cost per user decreased 50%

## Phase 3: Performance Optimization (150K → 220K users)

### Database Query Optimization Deep Dive

Even with read replicas and caching, some queries were still slow. We profiled everything:

**Finding Slow Queries:**

```sql
-- Enable query logging
ALTER SYSTEM SET log_min_duration_statement = 100;  -- Log queries > 100ms

-- Check pg_stat_statements
SELECT query, calls, total_time, mean_time, max_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
```

**Optimization 1: Add Strategic Indexes**

```sql
-- Before: Full table scan (2.3s)
SELECT * FROM user_progress
WHERE user_id = 12345 AND course_id = 67;

-- Add composite index
CREATE INDEX idx_user_progress_user_course
ON user_progress(user_id, course_id);

-- After: Index scan (12ms)
```

**Optimization 2: Materialized Views**

For expensive analytics queries:

```sql
-- Create materialized view for dashboard stats
CREATE MATERIALIZED VIEW dashboard_stats AS
SELECT
    u.id as user_id,
    COUNT(DISTINCT up.course_id) as courses_started,
    SUM(up.completed_modules) as total_modules_completed,
    AVG(up.quiz_score) as avg_quiz_score
FROM users u
LEFT JOIN user_progress up ON u.id = up.user_id
GROUP BY u.id;

-- Add index
CREATE UNIQUE INDEX ON dashboard_stats(user_id);

-- Refresh periodically (via cron)
REFRESH MATERIALIZED VIEW CONCURRENTLY dashboard_stats;
```

**Result:**
- Dashboard query: 3.2s → 50ms
- Refreshed every 5 minutes (acceptable staleness for analytics)

### API Response Time Optimization

**Optimization 1: Compression**

```javascript
const compression = require('compression');
app.use(compression());  // Gzip responses
```

**Impact:** Response size reduced 70% for JSON APIs

**Optimization 2: Pagination**

```javascript
// Before: Return all 10,000 courses
app.get('/api/courses', async (req, res) => {
    const courses = await Course.findAll();
    res.json(courses);  // 15 MB response 😱
});

// After: Paginate
app.get('/api/courses', async (req, res) => {
    const page = parseInt(req.query.page) || 1;
    const limit = 50;
    const offset = (page - 1) * limit;

    const courses = await Course.findAll({ limit, offset });
    const total = await Course.count();

    res.json({
        data: courses,
        page,
        total_pages: Math.ceil(total / limit),
        total_items: total
    });
});
```

**Impact:**
- Response size: 15 MB → 100 KB
- Load time: 8s → 200ms

**Optimization 3: Lazy Loading & Code Splitting**

Frontend optimization was critical:

```javascript
// Before: Load everything upfront
import Dashboard from './Dashboard';
import Courses from './Courses';
import Quiz from './Quiz';

// After: Lazy load with React.lazy
const Dashboard = React.lazy(() => import('./Dashboard'));
const Courses = React.lazy(() => import('./Courses'));
const Quiz = React.lazy(() => import('./Quiz'));

function App() {
    return (
        <Suspense fallback={<LoadingSpinner />}>
            <Routes>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/courses" element={<Courses />} />
                <Route path="/quiz" element={<Quiz />} />
            </Routes>
        </Suspense>
    );
}
```

**Impact:**
- Initial bundle size: 2.5 MB → 400 KB
- Time to interactive: 5s → 1.2s

## Phase 4: Monitoring & Observability

### The Philosophy

**You can't improve what you don't measure.**

We implemented comprehensive monitoring:

**Metrics to Track:**

1. **Infrastructure Metrics:**
   - CPU, memory, disk I/O
   - Network throughput
   - Container health

2. **Application Metrics:**
   - Request latency (p50, p95, p99)
   - Error rates
   - Throughput (requests per second)

3. **Business Metrics:**
   - Active users
   - Sign-ups
   - Course completions
   - Revenue

### Custom CloudWatch Dashboards

```python
import boto3
from datetime import datetime

cloudwatch = boto3.client('cloudwatch')

def log_custom_metric(metric_name, value, unit='Count'):
    cloudwatch.put_metric_data(
        Namespace='RevisionDojo/API',
        MetricData=[
            {
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit,
                'Timestamp': datetime.utcnow()
            }
        ]
    )

# Example usage in API
@app.post('/api/quiz/submit')
async def submit_quiz(quiz_data):
    start_time = time.time()

    # Process quiz
    result = process_quiz(quiz_data)

    # Log metrics
    latency = (time.time() - start_time) * 1000  # ms
    log_custom_metric('QuizSubmissionLatency', latency, 'Milliseconds')
    log_custom_metric('QuizSubmissions', 1, 'Count')

    return result
```

### Alerting Strategy

**Critical Alerts (PagerDuty):**
- API error rate > 1%
- Database connections exhausted
- P95 latency > 2s
- Any 5xx errors

**Warning Alerts (Slack):**
- CPU > 80% for 5 minutes
- Disk usage > 85%
- Memory > 90%

**Alert Fatigue:**

We learned the hard way—too many alerts = ignoring all alerts.

**Solution:** Implement alert thresholds carefully and tune over time.

## Key Lessons Learned

### 1. **Database is Usually the Bottleneck**

**Before optimizing anything else:**
- Profile your queries
- Add strategic indexes
- Implement connection pooling
- Use read replicas

### 2. **Caching is a Force Multiplier**

**But be careful:**
- Cache invalidation is hard
- Set appropriate TTLs
- Monitor cache hit rates
- Have a strategy for cache warming

### 3. **Horizontal Scaling > Vertical Scaling**

**Benefits:**
- Better fault tolerance
- More cost-effective at scale
- Easier to scale incrementally

**Trade-offs:**
- More complex deployments
- Need load balancing
- Stateless applications required

### 4. **Monitoring is Non-Negotiable**

**You need:**
- Real-time metrics
- Alerting that actually works
- Historical data for trend analysis
- Business metrics tied to technical metrics

### 5. **Infrastructure as Code Saves Lives**

**Benefits:**
- Reproducible environments
- Version-controlled infrastructure
- Easy rollbacks
- Documentation as code

### 6. **Move Fast, But Measure Everything**

YC teaches you to ship quickly. But measure:
- User engagement
- Error rates
- Performance metrics
- Business KPIs

**Iteration speed matters, but only if you're iterating in the right direction.**

## The Results

After 6 months:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Users Supported | 10K | 220K | 22x |
| P95 API Latency | 5s | 250ms | 20x faster |
| Database CPU | 80% | 25% | 3.2x more headroom |
| Error Rate | 0.5% | 0.02% | 25x lower |
| Cost per User | $0.05 | $0.009 | 5.5x cheaper |

## What's Next?

We're not done. Next challenges:

1. **Multi-region deployment** for better global latency
2. **GraphQL** to reduce API calls and over-fetching
3. **Event-driven architecture** with message queues
4. **Kubernetes migration** for more sophisticated orchestration

## Final Thoughts

Scaling isn't about choosing the "best" technology. It's about:
- Understanding your constraints
- Measuring what matters
- Iterating based on data
- Making pragmatic tradeoffs

We went from 10K to 220K users using PostgreSQL, Redis, Node.js, and AWS. Nothing exotic. No fancy distributed databases. Just fundamentals executed well.

**The best architecture is the one that meets your current needs while being flexible enough to evolve.**

---

## Want to Learn More?

- [GitHub: Sales Forecasting Platform](https://github.com/tonesgainz/sales-forecasting)
- [Connect on LinkedIn](https://linkedin.com/in/tonenv)
- [Follow me on Twitter](https://twitter.com/tonesgainz)

**Questions?** Drop a comment or email me at tony@snfactor.com

---

*Tony V. Nguyen is a DevOps Engineer at RevisionDojo (YC W24) and founder of SNF Global LLC. He's passionate about building scalable infrastructure and helping engineers level up their skills.*
