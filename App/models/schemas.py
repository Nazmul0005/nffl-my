from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class Team(BaseModel):
    id: str
    name: str
    market: str
    alias: str = Field(..., description="Team abbreviation")
    
class Player(BaseModel):
    id: str
    name: str
    position: str
    jersey_number: Optional[str] = None
    
class Game(BaseModel):
    id: str
    status: str
    scheduled: str
    home_team: Team
    away_team: Team
    
class Schedule(BaseModel):
    year: int
    season_type: str
    games: List[Game]
    
class TeamProfileResponse(BaseModel):
    team: Team
    players: List[Player]
    
class PlayerProfileResponse(BaseModel):
    player: Player
    team: Optional[Team] = None
    
class ErrorResponse(BaseModel):
    detail: str

# Change from NFLquery to NFLQuery to match imports
class NFLQuery(BaseModel):
    query: str = Field(..., description="Natural language question about NFL data")

class NFLQueryResponse(BaseModel):
    query: str
    answer: str
    data_sources: List[str]
    
class TeamResponse(BaseModel):
    team_code: str
    team_name: str
    logo_small: str
    logo_medium: str
    logo_standard: str
    logo_helmet: str
    
class NewsArticle(BaseModel):
    article_headline: str
    article_date: str
    article_author: str
    article_excerpt: str
    article_link: str
    playerIds: List[int]
    teams: List[str]