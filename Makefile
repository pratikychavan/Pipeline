clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +

migrate:
	python manage.py makemigrations
	python manage.py migrate

# user:
# 	python manage.py createsuperuser \
# 	--no-input \
# 	--username=admin \
# 	--email=admin@admin.com
# 	printf "admin123\nadmin123\n" | python manage.py changepassword admin

server:
	python manage.py runserver