# NFL Fantasy Data API

A FastAPI application that fetches and displays NFL fantasy football data from the Fantasy Nerds API.

## Features

- Fetch NFL teams and players data
- Get NFL schedules and standings
- Access fantasy draft rankings and projections
- View player tiers and auction values
- Check weekly projections and rankings
- Get defensive rankings and depth charts
- View injury reports and news
- Track player adds/drops for waiver wire activity
- Check weather forecasts for games
- Rest-of-season (ROS) player projections
- Best ball and dynasty league rankings
- Intelligent API caching to reduce Fantasy Nerds API calls
- Natural language queries for fantasy football insights
- Swagger UI for API documentation and testing

## Project Structure

```
NFL_data_retrieved/
├── .env                  # Environment variables
├── requirements.txt      # Project dependencies
├── main.py               # FastAPI application entry point
├── App/                  # Main application package
│   ├── api/              # API endpoints
│   │   └── routes.py     # Route handlers
│   ├── core/             # Core functionality
│   │   └── config.py     # Application configuration
│   ├── models/           # Data models
│   │   └── schemas.py    # Pydantic schemas
│   └── services/         # Service layer
│       └── nfl_service.py  # NFL data service
```

## Setup

1. Clone the repository
2. Create a `.env` file with your Fantasy Nerds API key:
   ```
   FANTASY_NERDS_API_KEY=your_api_key_here
   # Default key is: ABWTFKDMZU3G6SDPGMMY
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Run the application:
   ```
   uvicorn main:app --reload
   ```

## API Documentation

Once the server is running, you can access:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Endpoints

### Core Endpoints
- `GET /nfl/teams` - Get all NFL teams
- `GET /nfl/schedule` - Get NFL schedule
- `GET /nfl/standings` - Get current standings
- `GET /nfl/injuries` - Get injury reports
- `GET /nfl/players` - Get NFL players list
- `DELETE /nfl/cache` - Clear API cache

### Fantasy Football Endpoints
- `GET /nfl/draft-rankings` - Get draft rankings
- `GET /nfl/draft-projections` - Get draft projections
- `GET /nfl/player-tiers` - Get player tiers
- `GET /nfl/auction-values` - Get auction values
- `GET /nfl/adp` - Get average draft position
- `GET /nfl/best-ball` - Get best ball rankings
- `GET /nfl/bye-weeks` - Get bye weeks
- `GET /nfl/defense-rankings` - Get defensive rankings
- `GET /nfl/depth` - Get depth charts
- `GET /nfl/weekly-projections` - Get weekly projections
- `GET /nfl/weekly-rankings` - Get weekly rankings
- `GET /nfl/dynasty` - Get dynasty rankings
- `GET /nfl/news` - Get NFL news
- `GET /nfl/fantasy-leaders` - Get fantasy leaders
- `GET /nfl/add-drops` - Get player adds/drops
- `GET /nfl/weather` - Get weather forecasts
- `GET /nfl/ros` - Get rest-of-season projections

### Natural Language Query
- `POST /nfl/query` - Ask a natural language question about NFL data
