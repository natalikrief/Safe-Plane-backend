web: gunicorn -w 4 -k uvicorn.workers.UvicornWorker testFastAPI:app -t 60 --keep-alive 60

#web: gunicorn main.wsgi

# Uncomment this `release` process if you are using a database, so that Django's model
# migrations are run as part of app deployment, using Heroku's Release Phase feature:
# https://docs.djangoproject.com/en/5.0/topics/migrations/
# https://devcenter.heroku.com/articles/release-phase
#release: ./testFastAPI.py migrate --no-input
