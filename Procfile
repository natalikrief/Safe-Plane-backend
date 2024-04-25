web: gunicorn -w 4 -k uvicorn.workers.UvicornWorker testFastAPI:app --timeout 600 -t 600 --keep-alive 600

#web: uvicorn testFastAPI:app --config-file uvicorn_conf.py

#web: uvicorn testFastAPI:app --host=0.0.0.0 --port=${PORT} --keep-alive-timeout 60 --timeout-keep-alive 60



#web: gunicorn main.wsgi

# Uncomment this `release` process if you are using a database, so that Django's model
# migrations are run as part of app deployment, using Heroku's Release Phase feature:
# https://docs.djangoproject.com/en/5.0/topics/migrations/
# https://devcenter.heroku.com/articles/release-phase
#release: ./testFastAPI.py migrate --no-input
