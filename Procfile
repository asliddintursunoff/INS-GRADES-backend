web: uvicorn app.main:app --host=0.0.0.0 --port=8000
worker: celery -A app.worker.notification_scheduler worker --beat --pool=solo -l info
flower: celery -A app.worker.notification_scheduler flower --port=5555 --basic_auth=admin:password
