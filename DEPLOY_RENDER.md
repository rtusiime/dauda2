# Deploying to Render

## Prerequisites
1. Render account (sign up at https://render.com)
2. GitHub account (recommended for easier deployment)
3. Your Airbnb and Booking.com credentials

## Deployment Steps

### Option 1: Deploy from GitHub (Recommended)

1. **Push your code to GitHub**
   - Create a new repository on GitHub
   - Push this code (credentials.json will be ignored automatically)

2. **Connect to Render**
   - Log into Render (https://dashboard.render.com)
   - Click "New +" → "Blueprint"
   - Connect your GitHub repository
   - Render will automatically detect the `render.yaml` file

3. **Set Environment Variables**
   - In the Render dashboard, go to your service
   - Navigate to "Environment" section
   - Add these secret variables:
     - `AIRBNB_EMAIL` - your Airbnb email
     - `AIRBNB_PASSWORD` - your Airbnb password
     - `BOOKING_EMAIL` - your Booking.com email
     - `BOOKING_PASSWORD` - your Booking.com password

4. **Deploy**
   - Render will automatically build and deploy
   - Wait for the build to complete (may take 5-10 minutes for first deploy)
   - Your app will be available at: `https://calendar-sync-api.onrender.com`

### Option 2: Deploy with Docker

1. **Create New Web Service**
   - Log into Render dashboard
   - Click "New +" → "Web Service"
   - Connect your repository

2. **Configure Service**
   - Environment: Docker
   - Dockerfile Path: `./Dockerfile`
   - Add the environment variables as described above

### After Deployment

Your API will be available at your Render URL:
- Dashboard: `https://your-app.onrender.com/`
- API Docs: `https://your-app.onrender.com/docs`
- Health Check: `https://your-app.onrender.com/api/bookings`

## Important Notes

- **Free Tier**: Render free tier spins down after 15 minutes of inactivity. First request after idle may take 30-60 seconds.
- **Persistent Storage**: The disk volume ensures your database persists between deploys.
- **Security**: Never commit credentials.json or .env files. Always use environment variables in production.
- **Logs**: View logs in the Render dashboard under your service → "Logs" tab

## Troubleshooting

- **Build fails**: Check the logs in Render dashboard
- **Playwright errors**: The Dockerfile installs all required dependencies
- **Database issues**: The persistent disk is mounted at `/app/data`

## Sharing with Your Team

Once deployed, share the URL with your team:
```
https://your-app-name.onrender.com
```

They can access:
- Web dashboard to view/manage bookings
- API endpoints to integrate with other tools
