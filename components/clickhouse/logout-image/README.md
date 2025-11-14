# Logout Image

This directory contains the small web service used to trigger **real Cognito logout** in the Adage/Karma observability stack.

AWS ALB cannot forward POST requests to Cognito’s `/logout` endpoint directly, and it cannot add both the `client_id` and `logout_uri` query parameters required by Cognito.
This container solves that limitation.

The logout flow becomes:

1. User visits  
   `/logout` on any protected site (e.g., Grafana)
2. ALB forwards the request to this container.
3. The container redirects the user to the correct Cognito logout endpoint.
4. Cognito clears the user's session.
5. Cognito sends the user back to your landing page.

## Features

- Lightweight Python Flask app
- Handles GET `/logout` and redirects to Cognito
- Works with ECS + ALB routing
- Provides real Cognito logout

## Environment Variables

- `COGNITO_DOMAIN`
- `AWS_REGION`
- `COGNITO_CLIENT_ID`
- `LOGOUT_REDIRECT_URI`

## Running Locally

```
docker build -t logout-service .
docker run -p 8080:8080 \
  -e COGNITO_DOMAIN=cognito-usekarma-sso \
  -e AWS_REGION=us-east-1 \
  -e COGNITO_CLIENT_ID=your_client_id \
  -e LOGOUT_REDIRECT_URI=https://grafana.usekarma.dev/ \
  logout-service
```

Visit: `http://localhost:8080/logout`

## Building and Pushing to ECR

```
./build.sh
```

## ECS Integration

Route `/logout` to this service via ALB.
