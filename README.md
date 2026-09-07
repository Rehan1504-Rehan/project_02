# Northstar Store — Django E-Commerce

Northstar Store is a real, beginner-friendly Django 5 e-commerce application. It uses Django templates and Bootstrap 5 for the storefront, Django Admin for store operations, SQLite for local development, and PostgreSQL automatically when Railway provides a `DATABASE_URL`.

It is intentionally a simple order system: customers can place an order with shipping details, but no fake payment gateway is included.

## Features

- Customer registration with first name, last name, unique email validation, and Django password hashing.
- Login with either username or email, plus secure session logout.
- Product catalog with categories, product images, inventory, availability, sale pricing, and historical prices.
- Product search across name, description, and category.
- Category filtering.
- Persistent database cart for authenticated customers.
- Quantity validation so customers cannot add or order more than available stock.
- Transaction-safe checkout with locked inventory rows.
- Orders and order items stored permanently in the database.
- Order items save the product name and price at purchase time. Later product price changes do not change old orders.
- Customer order history and order detail pages.
- Customized Django Admin for products, images, categories, users, carts, orders, and order status.
- Product image preview in Admin.
- WhiteNoise static files, Gunicorn, PostgreSQL configuration through `DATABASE_URL`, and Railway deployment files.
- Friendly 403, 404, and 500 pages.
- Responsive Bootstrap 5 storefront for desktop, tablet, and mobile.

## Folder structure

```text
project_02/
├── manage.py
├── requirements.txt
├── Procfile
├── runtime.txt
├── railway.json
├── .gitignore
├── .env.example
├── README.md
├── ecommerce/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── store/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── context_processors.py
│   ├── forms.py
│   ├── models.py
│   ├── urls.py
│   ├── views.py
│   ├── migrations/
│   │   ├── __init__.py
│   │   ├── 0001_initial.py
│   │   └── 0002_alter_orderitem_product_name.py
│   └── management/
│       ├── __init__.py
│       └── commands/
│           ├── __init__.py
│           └── create_admin.py
├── templates/
│   ├── 403.html
│   ├── 404.html
│   ├── 500.html
│   └── store/
│       ├── base.html
│       ├── home.html
│       ├── product_list.html
│       ├── product_detail.html
│       ├── register.html
│       ├── login.html
│       ├── cart.html
│       ├── checkout.html
│       ├── order_list.html
│       ├── order_detail.html
│       └── includes/product_card.html
├── static/
│   └── store/
│       ├── css/site.css
│       └── js/site.js
└── media/
    └── (created automatically; ignored by Git)
```

## Requirements

- Python 3.12 recommended (the repository includes `runtime.txt`).
- `pip`.
- SQLite locally, which is included with Python.
- PostgreSQL 13+ for production, supplied by Railway or another PostgreSQL host.

## Local setup on Windows

Open PowerShell or Command Prompt in the folder that contains `manage.py`.

### 1. Create and activate a virtual environment

PowerShell:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

Command Prompt:

```bat
python -m venv venv
venv\Scripts\activate
```

If PowerShell blocks activation, run this once in an Administrator PowerShell, or use Command Prompt:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 2. Install the dependencies

```bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Create local environment variables

Copy `.env.example` to `.env` for local configuration and replace its placeholder values. The project loads that ignored `.env` file with `python-dotenv`; Railway variables still take precedence because they are already present in the environment. A brand-new local checkout also works without any variables because it uses a random development `SECRET_KEY`, `DEBUG=True`, and SQLite.

For a PowerShell session, example values are:

```powershell
$env:SECRET_KEY = "replace-this-with-a-long-random-development-key"
$env:DEBUG = "True"
$env:ALLOWED_HOSTS = "localhost,127.0.0.1"
```

Do not commit a real `.env` file. It is ignored by Git.

### 4. Create the database tables

```bat
python manage.py makemigrations
python manage.py migrate
```

The repository already includes the initial migration. Running `makemigrations` again should report that there are no changes.

### 5. Create the administrator

Set the credentials only in your terminal, then run the safe custom command:

PowerShell:

```powershell
$env:ADMIN_USERNAME = "ADMIN"
$env:ADMIN_PASSWORD = "use-a-long-private-password-here"
$env:ADMIN_EMAIL = "admin@example.com"
python manage.py create_admin
```

Command Prompt:

```bat
set ADMIN_USERNAME=ADMIN
set ADMIN_PASSWORD=use-a-long-private-password-here
set ADMIN_EMAIL=admin@example.com
python manage.py create_admin
```

The command creates a Django superuser only if that username does not already exist. If it already exists, it makes no changes. The password is hashed by Django and is never stored in source code.

You can also create an admin interactively with `python manage.py createsuperuser`, but the environment-variable command is more convenient for Railway.

### 6. Run the development server

```bat
python manage.py runserver
```

Open:

- Storefront: <http://127.0.0.1:8000/>
- Admin dashboard: <http://127.0.0.1:8000/admin/>

## Using the site

### Add the first product

1. Open `/admin/` and sign in with the superuser credentials.
2. Select **Categories** and create a category such as `Electronics`.
3. Select **Products** and choose **Add product**.
4. Enter a name and description, price, optional discount price, stock quantity, and category.
5. Upload an image if desired.
6. Leave **Available** selected when the product should be visible to customers.
7. Click **Save**. The product appears on the home page and Shop all page if it has stock.

The admin list supports search, category/availability/date filters, inline price and inventory edits, and product image previews.

### Customer flow

1. A customer opens **Join us** and completes the registration form.
2. The user is permanently saved in Django's `auth_user` database table. Passwords are hashed using Django's password hasher.
3. The customer signs in with username or email.
4. They search or filter products, open details, choose a quantity, and add items to the database cart.
5. The cart prevents quantities above available stock.
6. Checkout validates the shipping address and phone number and creates the order in one database transaction.
7. Stock is reduced, the cart is cleared, and the order appears under **My orders**.

No payment gateway is simulated. Add a real payment provider only as a separate, deliberate feature.

### Update products and order status

In Admin, open **Products** to change prices, discount prices, descriptions, category, image, availability, and stock. Open **Orders** to review shipping information and change the status to Processing, Shipped, Delivered, or Cancelled. Old orders keep their `OrderItem.price` snapshot even after a catalog price edit.

## Environment variables

| Variable | Local example | Production guidance |
| --- | --- | --- |
| `SECRET_KEY` | `a-long-random-string` | Required secret; never commit it. |
| `DEBUG` | `True` | Set `False`. |
| `DATABASE_URL` | empty for SQLite | Railway PostgreSQL supplies this automatically. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Include the Railway public domain, comma separated. |
| `CSRF_TRUSTED_ORIGINS` | empty | Use full HTTPS origins, for example `https://your-app.up.railway.app`. |
| `ADMIN_USERNAME` | `ADMIN` | Private Railway variable. |
| `ADMIN_PASSWORD` | empty in Git | Private Railway variable; use a strong password. |
| `ADMIN_EMAIL` | `admin@example.com` | Private Railway variable. |
| `SECURE_SSL_REDIRECT` | `False` locally | Set `True` only when HTTPS proxy configuration is ready. |
| `MEDIA_ROOT` | default `media/` | Optional persistent mount such as `/data/media` (Render Persistent Disk) or `/app/media` (Railway Volume). |
| `SERVE_MEDIA` | `True` | Media is served automatically by Django. Set `False` when using external cloud object storage. |

Django will use SQLite when `DATABASE_URL` is empty. When `DATABASE_URL` is set, `dj-database-url` configures the database, including Railway's PostgreSQL URL.

## Railway deployment

### 1. Push the project to GitHub

Create an empty GitHub repository, then from this project directory run the commands below. Replace only `YOUR_GITHUB_REPOSITORY_URL` with the HTTPS or SSH URL copied from your new GitHub repository:

```bat
git init
git add .
git commit -m "Initial Django ecommerce project"
git branch -M main
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

For example, the remote line could become:

```bat
git remote add origin https://github.com/your-user/northstar-store.git
```

Do not replace the project code with the URL; replace the placeholder only in the `git remote add origin ...` command.

### 2. Create the Railway project

1. Go to <https://railway.app> and create a new project.
2. Choose **Deploy from GitHub repo** and select this repository.
3. Railway detects the `Procfile` and `runtime.txt` and runs Gunicorn with `ecommerce.wsgi`.
4. Click **New** → **Database** → **Add PostgreSQL**. Railway makes the database connection available to the application as `DATABASE_URL` when the PostgreSQL service is linked to the web service.

### 3. Add variables to the Railway web service

Open the web service (not only the PostgreSQL service), choose **Variables**, and add these values:

```text
SECRET_KEY=<generate-a-long-random-secret>
DEBUG=False
ALLOWED_HOSTS=<your-railway-domain>,<optional-custom-domain>
CSRF_TRUSTED_ORIGINS=https://<your-railway-domain>
ADMIN_USERNAME=ADMIN
ADMIN_PASSWORD=<strong-private-admin-password>
ADMIN_EMAIL=admin@example.com
SECURE_SSL_REDIRECT=False
```

Use Railway's **Generate** option for `SECRET_KEY` if available. Replace the angle-bracket values with real deployment values. Do not put the password in GitHub, README files, HTML, JavaScript, or Python source.

`ALLOWED_HOSTS` is a comma-separated list without `https://`. `CSRF_TRUSTED_ORIGINS` is a comma-separated list of full origins with `https://`.

### 4. Run database and setup commands

After the PostgreSQL service is linked and variables are saved, open the web service's Railway shell and run:

```text
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py create_admin
```

The `create_admin` command reads `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and `ADMIN_EMAIL` from Railway Variables. Running it again is safe: if the username exists, it does nothing.

You can rerun these commands after a deployment. For repeatable automated deployments, use them as a Railway pre-deploy/release command in your service configuration. Keep `create_admin` after migrations and keep the password only in Railway Variables.

### 5. Generate a public domain

In the Railway web service, open **Settings** → **Networking** → **Generate Domain**. Put that hostname into `ALLOWED_HOSTS` and its `https://` origin into `CSRF_TRUSTED_ORIGINS`, then redeploy. Open the generated public URL and test `/`, `/register/`, and `/admin/`.

### 6. Static files and media files

- WhiteNoise serves files collected into `staticfiles/`; the Procfile starts Gunicorn with the correct WSGI module.
- `python manage.py collectstatic --noinput` is safe to run during deployment.
- Product uploads go to `MEDIA_ROOT` and are served by Django at `/media/` in development and production (`SERVE_MEDIA` defaults to `True`).
- Cloud host container filesystems (e.g. Render, Railway) are ephemeral and not a permanent media store across redeploys.
  - **Render**: Attach a Persistent Disk mounted at `/data/media` and add `MEDIA_ROOT=/data/media` to the service environment variables.
  - **Railway**: Attach a Volume mounted at `/app/media` and add `MEDIA_ROOT=/app/media` to the service environment variables.
  - The application automatically serves the mounted disk/volume at `/media/`.
- For a multi-instance or higher-traffic shop, use an S3-compatible object store (Amazon S3, Cloudflare R2, or similar) and add a dedicated Django storage backend such as `django-storages`. Configure that backend and its bucket credentials as private service variables; never place cloud keys in this repository. Static files can continue to use WhiteNoise.

## Database and price behavior

The checkout uses `transaction.atomic()` and locks the cart and product rows while validating inventory. It creates the `Order`, all `OrderItem` rows, reduces stock, and clears the cart as one unit. If validation fails, no partial order remains.

Each `OrderItem` has:

- `product`: a nullable reference to the current catalog product;
- `product_name`: a readable name snapshot;
- `price`: the exact price at the time of purchase;
- `quantity`.

The order pages render `OrderItem.price`, not the current `Product.price`, so changing a product's price later cannot rewrite an old order.

## Testing and useful commands

Run Django's checks, migrations, static collection, and the test suite:

```bat
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py test
```

Check which migrations are applied:

```bat
python manage.py showmigrations
```

Start Gunicorn locally (PowerShell or Command Prompt):

```bat
gunicorn ecommerce.wsgi --log-file -
```

On Windows, Gunicorn is primarily intended for Railway/Linux. Use `python manage.py runserver` for local Windows development.

## Troubleshooting

### `DisallowedHost` on Railway

Add the exact generated Railway hostname, without `https://`, to `ALLOWED_HOSTS`, save the variable, and redeploy.

### CSRF verification failed

Set `CSRF_TRUSTED_ORIGINS` to the full URL, including `https://`, for the public Railway domain. Do not use a bare hostname in this setting.

### Database connection errors

Confirm PostgreSQL is linked to the web service and that `DATABASE_URL` appears in the service variables. Run `python manage.py migrate` from the web service shell, not only from the database service.

### Images disappear after a redeploy

That is expected for ephemeral container storage. On Render, attach a Persistent Disk at `/data/media` and set `MEDIA_ROOT=/data/media`. On Railway, attach a Volume at `/app/media` and set `MEDIA_ROOT=/app/media`. Alternatively, configure S3-compatible object storage as described above.

### Static assets are missing

Run `python manage.py collectstatic --noinput`, confirm `DEBUG=False` is not combined with a missing `STATIC_ROOT`, and check that the service uses `gunicorn ecommerce.wsgi` from the project directory.

### Admin login does not work

Run migrations, confirm the Railway variables are set on the web service, and run `python manage.py create_admin` again. An existing username is intentionally not changed by the command; use Django's password reset workflow or create a different admin account if needed.

### `discount_price` validation error

A discount price must be lower than the regular price. Leave it blank for a product with no discount.

## Security notes

- Never commit `.env`, database credentials, `SECRET_KEY`, or the admin password.
- CSRF tokens are included on all state-changing storefront forms.
- The admin uses Django's built-in permission and password systems.
- Production should use `DEBUG=False`, HTTPS, a restricted `ALLOWED_HOSTS`, a trusted CSRF origin list, and persistent media storage.
