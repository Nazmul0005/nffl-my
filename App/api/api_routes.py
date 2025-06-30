
from fastapi import APIRouter, HTTPException, Path, Depends
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
import functools

from App.services.nfl_service import nfl_service
from App.models.schemas import ErrorResponse
from App.services.Nfl_query_service import nfl_query_service
from App.models.schemas import NFLQuery, NFLQueryResponse, ErrorResponse, TeamResponse, NewsArticle

# Simple in-memory cache for API responses
cache = {}
CACHE_EXPIRY = timedelta(minutes=15)  # Cache expiry time

def with_cache(expiry: Optional[timedelta] = None):
    """
    Decorator to cache API responses
    
    Args:
        expiry: Optional time delta for cache expiry (default: 15 minutes)
    """
    if expiry is None:
        expiry = CACHE_EXPIRY
        
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Create a cache key from function name and arguments
            key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Check if we have a cached response and it's still valid
            if key in cache:
                timestamp, value = cache[key]
                if datetime.now() - timestamp < expiry:
                    return value
            
            # Call the original function if no cache hit
            result = await func(*args, **kwargs)
            
            # Cache the result
            cache[key] = (datetime.now(), result)
            return result
        return wrapper
    return decorator

router = APIRouter(prefix="/nfl", tags=["NFL Data"])

@router.get("/teams", response_model=List[TeamResponse], summary="Get NFL Teams List")
@with_cache(timedelta(hours=24))  # Teams don't change often, cache for 24 hours
async def get_teams():
    """
    Retrieve all NFL teams.
    """
    return await nfl_service.get_teams()

@router.get("/schedule", response_model=dict, summary="Get NFL Schedule")
@with_cache(timedelta(hours=12))  # Schedule might update, cache for 12 hours
async def get_schedule():
    """
    Retrieve the current regular season schedule.
    """
    return await nfl_service.get_schedule()

@router.delete("/cache", summary="Clear API Cache")
async def clear_cache():
    """
    Clear all cached API responses.
    """
    cache.clear()
    return {"message": "Cache cleared successfully"}


@router.get("/standings", response_model=dict, summary="Get NFL Standings")
@with_cache(timedelta(hours=1))
async def get_standings():
    """
    Retrieve the current regular-season standings for all NFL teams including their rankings within their division and conference.
    """
    try:
        result = await nfl_service.get_standings()
        # Ensure we always return a dictionary
        if not isinstance(result, dict):
            return {"standings": {}, "message": "No standings data available"}
        return result
    except Exception as e:
        print(f"Error in standings endpoint: {str(e)}")
        return {"standings": {}, "message": f"Error retrieving standings data: {str(e)}"}

@router.get("/injuries", response_model=dict, summary="Get Injury Reports")
@with_cache(timedelta(hours=6))
async def get_weekly_injuries(season: Optional[int] = None, week: Optional[int] = None):
    """
    Retrieve injury reports for all NFL teams.
    
    - **season**: Optional season year (e.g., 2024 or 2023)
    - **week**: Optional week number (1-18)
    """
    return await nfl_service.get_weekly_injuries(season, week)


@router.get("/draft-rankings", response_model=dict, summary="Get NFL Draft Rankings")
@with_cache(timedelta(hours=6))
async def get_draft_rankings(format: str = "std"):
    """
    Retrieve draft rankings and injury risk for the current season.
    
    - **format**: The scoring format (std = standard scoring, ppr = point per reception, half = half-point-ppr, superflex = Superflex 2 QB)
    """
    return await nfl_service.get_draft_rankings(format)

@router.get("/player-tiers", response_model=dict, summary="Get NFL Player Tiers")
@with_cache(timedelta(hours=6))
async def get_player_tiers(format: str = "std"):
    """
    Retrieve player tiers for value-based drafting.
    
    - **format**: The scoring format (std = standard scoring, ppr = point per reception)
    """
    return await nfl_service.get_player_tiers(format)

@router.get("/auction-values", response_model=dict, summary="Get Auction Values")
@with_cache(timedelta(hours=6))
async def get_auction_values(teams: int = 12, budget: int = 200, format: str = "std"):
    """
    Retrieve fantasy football auction values.
    
    - **teams**: Number of teams in the league (8, 10, 12, 14, 16)
    - **budget**: League budget (default: 200)
    - **format**: Scoring format (std, ppr)
    """
    return await nfl_service.get_auction_values(teams, budget, format)

@router.get("/adp", response_model=dict, summary="Get Average Draft Position")
@with_cache(timedelta(hours=6))
async def get_adp(teams: int = 12, format: str = "std"):
    """
    Retrieve average draft position data.
    
    - **teams**: Number of teams in the league (8, 10, 12, 14, 16)
    - **format**: Scoring format (std, ppr, half, superflex)
    """
    return await nfl_service.get_adp(teams, format)

@router.get("/best-ball", response_model=dict, summary="Get Best Ball Rankings")
@with_cache(timedelta(hours=12))
async def get_best_ball_rankings():
    """
    Retrieve Best Ball rankings for the upcoming NFL season.
    """
    return await nfl_service.get_best_ball_rankings()

@router.get("/bye-weeks", response_model=dict, summary="Get Bye Weeks")
@with_cache(timedelta(hours=24))
async def get_bye_weeks():
    """
    Retrieve bye weeks for the current season.
    """
    return await nfl_service.get_bye_weeks()

@router.get("/defense-rankings", response_model=dict, summary="Get Defensive Rankings")
@with_cache(timedelta(hours=12))
async def get_defensive_rankings():
    """
    Retrieve defensive rankings for all NFL teams.
    """
    return await nfl_service.get_defensive_rankings()

@router.get("/depth", response_model=dict, summary="Get Depth Charts")
@with_cache(timedelta(hours=12))
async def get_depth_charts():
    """
    Retrieve current depth charts for all NFL teams.
    """
    return await nfl_service.get_depth_charts()

@router.get("/weekly-projections", response_model=dict, summary="Get Weekly Projections")
@with_cache(timedelta(hours=3))
async def get_weekly_projections():
    """
    Retrieve weekly projections for Weeks 1-18.
    """
    return await nfl_service.get_weekly_projections()

@router.get("/weekly-rankings", response_model=dict, summary="Get Weekly Rankings")
@with_cache(timedelta(hours=3))
async def get_weekly_rankings(format: str = "std"):
    """
    Retrieve current weekly rankings including projected points.
    
    - **format**: Scoring format (std, ppr, half)
    """
    return await nfl_service.get_weekly_rankings(format)

@router.get("/dynasty", response_model=dict, summary="Get Dynasty Rankings")
@with_cache(timedelta(hours=24))
async def get_dynasty_rankings():
    """
    Retrieve consensus dynasty rankings.
    """
    return await nfl_service.get_dynasty_rankings()

@router.get("/news", response_model=List[NewsArticle], summary="Get NFL News")
@with_cache(timedelta(hours=1))
async def get_nfl_news():
    """
    Retrieve current player and team news with fantasy analysis.
    """
    return await nfl_service.get_nfl_news()

@router.get("/fantasy-leaders", response_model=dict, summary="Get Fantasy Leaders")
@with_cache(timedelta(hours=3))
async def get_fantasy_leaders(format: str = "std", position: str = "ALL", week: int = 0):
    """
    Retrieve weekly and season leaders by total fantasy points.
    
    - **format**: Scoring format (std, ppr, half)
    - **position**: Position filter (ALL, QB, RB, WR, TE, FLEX, K, IDP)
    - **week**: Week number (0 for entire season, 1-18 for specific week)
    """
    return await nfl_service.get_fantasy_leaders(format, position, week)

@router.get("/players", summary="Get NFL Players")
@with_cache(timedelta(hours=24))
async def get_players(include_inactive: bool = False):
    """
    Get a list of current NFL players.
    
    - **include_inactive**: Set to True to include inactive players
    """
    try:
        data = await nfl_service.get_players(include_inactive)
        
        # Return the data directly
        return data
    except Exception as e:
        import traceback
        print(f"Error in get_players: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error retrieving players data: {str(e)}")

@router.get("/add-drops", response_model=dict, summary="Get Player Adds and Drops")
@with_cache(timedelta(hours=3))
async def get_player_adds_drops():
    """
    Retrieve the players most added and dropped over the previous 48 hours across all Yahoo, ESPN, CBS Sports, and Sleeper leagues.
    """
    return await nfl_service.get_player_adds_drops()

@router.get("/weather", response_model=dict, summary="Get Weather Forecasts")
@with_cache(timedelta(hours=3))
async def get_weather_forecasts():
    """
    Retrieve the weather forecasts for all NFL teams.
    """
    return await nfl_service.get_weather_forecasts()

@router.get("/draft-projections", response_model=dict, summary="Get Draft Projections")
@with_cache(timedelta(hours=24))
async def get_draft_projections():
    """
    Retrieve draft projections for the upcoming season.
    """
    return await nfl_service.get_draft_projections()

@router.get("/ros", response_model=dict, summary="Get Rest of Season Projections")
@with_cache(timedelta(hours=6))
async def get_rest_of_season_projections():
    """
    Retrieve rest of season (ROS) projections for all skill and IDP players.
    """
    return await nfl_service.get_rest_of_season_projections()

@router.get("/dfs", response_model=dict, summary="Get Daily Fantasy Football")
@with_cache(timedelta(hours=1))
async def get_dfs(slate_id: str):
    """
    Get the salaries, Fantasy Nerds projected points, and Bang for Your Buck scores 
    for FanDuel, DraftKings, and Yahoo for the current week.
    
    - **slate_id**: The slateId is required and can be obtained by calling the Daily Fantasy Football - Get Slates endpoint
    """
    return await nfl_service.get_dfs(slate_id)

@router.get("/dfs-slates", response_model=dict, summary="Get Daily Fantasy Football Slates")
@with_cache(timedelta(hours=1))
async def get_dfs_slates():
    """
    Get a listing of the current slates for upcoming DFS Classic contests (Weeks 1-18). 
    The slateId's from this response will be needed to retrieve player data for a specific slate.
    """
    return await nfl_service.get_dfs_slates()

@router.get("/idp-draft", response_model=dict, summary="Get IDP Draft Rankings")
@with_cache(timedelta(hours=24))
async def get_idp_draft():
    """
    Retrieve IDP (Individual Defensive Players) rankings for the upcoming NFL season.
    """
    return await nfl_service.get_idp_draft()

@router.get("/idp-weekly", response_model=dict, summary="Get IDP Weekly Projections")
@with_cache(timedelta(hours=6))
async def get_idp_weekly():
    """
    Retrieve weekly projections for IDP players.
    """
    return await nfl_service.get_idp_weekly()

@router.get("/nfl-picks", response_model=dict, summary="Get NFL Picks")
@with_cache(timedelta(hours=6))
async def get_nfl_picks():
    """
    Get the current week's NFL game picks for each game broken down by expert.
    """
    return await nfl_service.get_nfl_picks()

@router.get("/playoffs", response_model=dict, summary="Get Playoff Projections")
@with_cache(timedelta(hours=6))
async def get_playoff_projections(week: int):
    """
    Retrieve statistical projections for the NFL playoffs.
    
    - **week**: Pass the playoff week number (1 = Wild Card, 2 = Divisional Round, 3 = Conference Championships, 4 = Super Bowl)
    """
    return await nfl_service.get_playoff_projections(week)

@router.post("/query", response_model=NFLQueryResponse, summary="Ask a question about NFL data")
async def ask_nfl_question(query: NFLQuery):
    """
    Ask a natural language question about NFL data and get an AI-powered response with concurrent API calls for optimal performance.
    
    This endpoint uses parallel API calls to fetch data, resulting in significantly faster response times.
    
    Examples:
    - "Who are the top quarterbacks this season?"
    - "What's the injury status for the Chiefs this week?"
    - "Show me the Packers' upcoming schedule"
    - "What's the depth chart for the Cowboys?"
    - "Which teams are playing this weekend?"
    """
    response = await nfl_query_service.process_query(query.query)
    return response


