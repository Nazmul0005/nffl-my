from App.services.api_client import nfl_api_client
from App.services.LLm_service import llm_service
import re
import datetime
from typing import Dict, List, Any, Tuple, Optional

class NFLQueryService:
    """
    Service to handle user queries related to NFL data
    """

    def __init__(self):
        self.api_client = nfl_api_client
        self.llm_service = llm_service
        
        # Define team pattern dictionary for better team extraction
        self.team_patterns = {
            "cardinals": "ARI", "falcons": "ATL", "ravens": "BAL", "bills": "BUF",
            "panthers": "CAR", "bears": "CHI", "bengals": "CIN", "browns": "CLE",
            "cowboys": "DAL", "broncos": "DEN", "lions": "DET", "packers": "GB",
            "texans": "HOU", "colts": "IND", "jaguars": "JAX", "chiefs": "KC",
            "raiders": "LV", "chargers": "LAC", "rams": "LA", "dolphins": "MIA",
            "vikings": "MIN", "patriots": "NE", "saints": "NO", "giants": "NYG",
            "jets": "NYJ", "eagles": "PHI", "steelers": "PIT", "seahawks": "SEA",
            "49ers": "SF", "niners": "SF", "buccaneers": "TB", "bucs": "TB", 
            "titans": "TEN", "commanders": "WAS", "washington": "WAS"
        }

    async def process_query(self, query: str):
        """
        Process a natural language query about NFL data
        
        Args:
            query (str): The user's question about NFL data
            
        Returns:
            dict: Response containing the LLM's answer and relevant data
        """
        try:
            # Determine query type and fetch relevant data
            query_type, params = self._classify_query(query)
            context_data = await self._fetch_relevant_data(query_type, params)
            
            # Add detected player information to context_data metadata for the LLM service
            if "player" in params:
                if "metadata" not in context_data:
                    context_data["metadata"] = {}
                context_data["metadata"]["target_player"] = params["player"]
                print(f"DEBUG: Added target_player to context_data: {params['player']}")
            
            # Check if there was an error in fetching data
            if "error" in context_data and len(context_data) <= 2:  # Only error and query_type
                default_sources = self.get_data_sources(query_type)
                llm_response = f"I'm sorry, I couldn't retrieve the data needed to answer your question. Error: {context_data.get('error', 'Unknown error')}"
                
                return {
                    "query": query,
                    "answer": llm_response,
                    "data_sources": default_sources
                }
            
            # Track which endpoints were actually used in this query
            used_endpoints = []
            for key in context_data:
                if key not in ["query_type", "metadata", "original_query", "error"]:
                    # Convert the key to an endpoint name format
                    endpoint_name = key.replace("_", "-") if key != "league" else "teams"
                    endpoint_path = f"/nfl/{endpoint_name}"
                    if endpoint_path not in used_endpoints:
                        used_endpoints.append(endpoint_path)
            
            # Make sure we have at least one data source
            if not used_endpoints:
                used_endpoints = self.get_data_sources(query_type)
                
                # Ensure data_sources is always a list, never empty
                if not used_endpoints:
                    used_endpoints = ["Fantasy Nerds NFL API Data"]

            # Generate a LLM response with the context data
            llm_response = await self.llm_service.generate_response(query, context_data)

            return {
                "query": query,
                "answer": llm_response,
                "data_sources": used_endpoints
            }
            
        except Exception as e:
            # Fallback for any unexpected errors
            print(f"Error in process_query: {str(e)}")
            return {
                "query": query,
                "answer": f"I'm sorry, an unexpected error occurred while processing your question. Error: {str(e)}",
                "data_sources": ["Fantasy Nerds NFL API Data"]
            }
    
    def _classify_query(self, query: str) -> Tuple[str, Dict[str, Any]]:
        """
        Classify the user's query to determine the type of data needed and extract parameters
        
        Args:
            query (str): The user's question about NFL data
            
        Returns:
            tuple: A tuple containing the query type and parameters
        """
        # Store original query for player name detection (before lowercase conversion)
        original_query = query
        query = query.lower()
        params = {"original_query": query}
        
        # Extract year if present in query
        year_match = re.search(r'20\d{2}', query)
        if year_match:
            params["year"] = year_match.group(0)
        else:
            # Default to current year
            current_year = datetime.datetime.now().year
            params["year"] = str(current_year)
        
        # Extract week if mentioned
        week_match = re.search(r'week (\d+)', query)
        if week_match:
            params["week"] = week_match.group(1)
        else:
            # Determine current week based on the current date
            # This is a simplified approach - in production you would calculate the actual NFL week
            current_month = datetime.datetime.now().month
            current_day = datetime.datetime.now().day
            
            # Regular season typically starts in September
            if current_month < 9:
                params["week"] = "1"  # Preseason
            else:
                # Rough approximation - a better approach would use a lookup table or API
                week_num = ((current_month - 9) * 4) + (current_day // 7) + 1
                params["week"] = str(min(17, max(1, week_num)))  # Ensure between 1-17
        
        # Extract season type if mentioned
        if any(term in query for term in ["preseason", "pre-season", "pre season"]):
            params["season_type"] = "PRE"
        elif any(term in query for term in ["postseason", "post-season", "post season", "playoffs"]):
            params["season_type"] = "PST"
        else:
            # Determine season type based on current date
            current_month = datetime.datetime.now().month
            if current_month < 9:
                params["season_type"] = "PRE"  # Preseason before September
            elif current_month > 12 or current_month < 3:
                params["season_type"] = "PST"  # Postseason Jan-Feb
            else:
                params["season_type"] = "REG"  # Regular season Sep-Dec
            
        # Extract team mentions
        teams_found = []
        for team_name, team_code in self.team_patterns.items():
            if team_name in query:
                teams_found.append(team_code)
                
        if teams_found:
            params["teams"] = teams_found
            
        # Try to extract player names (improved approach)
        # First, look for player names with position prefixes (using original query for capitalization)
        prefix_pattern = r'(?:player|quarterback|qb|running back|rb|wide receiver|wr|tight end|te) ([A-Z][a-z]+ [A-Z][a-z]+)'
        prefix_match = re.search(prefix_pattern, original_query, re.IGNORECASE)
        if prefix_match:
            params["player"] = prefix_match.group(1)
        else:
            # Enhanced player name detection using pattern matching
            # Look for two consecutive capitalized words (likely a player name) in original query
            player_name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'
            player_matches = re.findall(player_name_pattern, original_query)
            
            if player_matches:
                # Take the first match as the player name
                params["player"] = player_matches[0]
                print(f"DEBUG: Found player name via regex: {player_matches[0]} in query: {original_query}")
            else:
                # Try to find standalone player names (common NFL players)
                common_players = [
                    "Patrick Mahomes", "Josh Allen", "Jalen Hurts", "Joe Burrow", "Lamar Jackson",
                    "Justin Herbert", "Trevor Lawrence", "Tua Tagovailoa", "Dak Prescott", "Aaron Rodgers",
                    "Christian McCaffrey", "Austin Ekeler", "Saquon Barkley", "Derrick Henry", "Jonathan Taylor",
                    "Justin Jefferson", "Ja'Marr Chase", "Tyreek Hill", "Stefon Diggs", "CeeDee Lamb",
                    "Travis Kelce", "Mark Andrews", "George Kittle", "T.J. Hockenson", "Dallas Goedert",
                    "Lenny Krieg", "Ollie Gordon", "Alex Hale"  # Added to support these specific players
                ]
                
                # Check if any of these names are in the query
                for player in common_players:
                    if player.lower() in query.lower():
                        params["player"] = player
                        print(f"DEBUG: Found common player {player} in query: {original_query}")
                        break
                    
                # Also check for last names of star players if they're unique enough
                if "player" not in params:
                    last_names = {
                        "mahomes": "Patrick Mahomes",
                        "allen": "Josh Allen",
                        "hurts": "Jalen Hurts",
                        "burrow": "Joe Burrow",
                        "jackson": "Lamar Jackson",
                        "herbert": "Justin Herbert",
                        "lawrence": "Trevor Lawrence",
                        "tagovailoa": "Tua Tagovailoa",
                        "prescott": "Dak Prescott",
                        "rodgers": "Aaron Rodgers",
                        "mccaffrey": "Christian McCaffrey",
                        "ekeler": "Austin Ekeler",
                        "barkley": "Saquon Barkley",
                        "henry": "Derrick Henry",
                        "taylor": "Jonathan Taylor",
                        "jefferson": "Justin Jefferson",
                        "chase": "Ja'Marr Chase",
                        "hill": "Tyreek Hill",
                        "diggs": "Stefon Diggs",
                        "lamb": "CeeDee Lamb",
                        "kelce": "Travis Kelce",
                        "andrews": "Mark Andrews",
                        "kittle": "George Kittle",
                        "hockenson": "T.J. Hockenson",
                        "goedert": "Dallas Goedert",
                        "krieg": "Lenny Krieg",
                        "gordon": "Ollie Gordon",
                        "hale": "Alex Hale"
                    }
                    
                    for last_name, full_name in last_names.items():
                        if last_name in query.lower():
                            params["player"] = full_name
                            print(f"DEBUG: Found player by last name {last_name} -> {full_name} in query: {original_query}")
                            break
        
        # Classify query type - check specific terms before general ones
        
        # Check for draft projections FIRST (before general "projections" check)
        if any(term in query for term in ["draft projection", "draft projections", "draft_projection", "draft_projections"]):
            return "draft_projections", params
            
        # Check if this is a player-specific query that should check multiple endpoints
        if "player" in params:
            print(f"DEBUG: Player detected in params: {params['player']}")
            # If a player is mentioned, default to player_rankings which will check multiple sources
            if any(term in query for term in ["ranking", "rank", "best", "top", "stats", "statistics", "projections", "projection"]):
                print(f"DEBUG: Returning player_rankings for query: {original_query}")
                return "player_rankings", params
            elif any(term in query for term in ["rest of season", "ros", "rest-of-season", "remaining games", "future projections", "vorp", "value over replacement"]):
                print(f"DEBUG: Returning ros_projections for query: {original_query}")
                return "ros_projections", params
            elif any(term in query for term in ["draft", "drafting", "draft pick", "adp", "average draft position"]):
                print(f"DEBUG: Returning draft_rankings for query: {original_query}")
                return "draft_rankings", params
            else:
                # For any other player query, use comprehensive player search
                print(f"DEBUG: Returning player_search for query: {original_query}")
                return "player_search", params
        else:
            print(f"DEBUG: No player detected in params for query: {original_query}")
            
        # Check for general rankings/projections (excluding draft projections already handled above)
        if any(term in query for term in ["ranking", "rank", "best", "top", "stats", "statistics"]) or \
           ("projections" in query and "draft" not in query):
            return "player_rankings", params
            
        if any(term in query for term in ["matchup", "vs", "versus", "against", "playing against", "face off", "game between"]):
            return "matchups", params
            
        # Check for VORP and ROS queries FIRST (before injury check to avoid "Hurts" matching "hurt")
        if any(term in query for term in ["rest of season", "ros", "rest-of-season", "remaining games", "future projections", "vorp", "value over replacement", "replacement player"]):
            return "ros_projections", params
              # Use word boundaries to avoid matching player names like "Hurts"
        injury_terms = ["injury", "injured", r"\bhurt\b", "sidelined", "out", "questionable", "probable"]
        if any(re.search(term if '\\b' in term else r'\b' + re.escape(term) + r'\b', query) for term in injury_terms):
            return "injuries", params
            
        if any(term in query for term in ["schedule", "upcoming", "games", "playing", "when", "calendar"]):
            return "schedule", params
            
        if any(term in query for term in ["depth chart", "roster", "lineup", "starters", "bench", "team composition"]):
            return "depth_chart", params
            
        if any(term in query for term in ["standings", "record", "win-loss", "win/loss", "division standing", "conference standing"]):
            return "standings", params
            
        if any(term in query for term in ["weather", "forecast", "rain", "temperature", "conditions"]):
            return "weather", params
            
        if any(term in query for term in ["adds", "drops", "pickups", "waiver", "transactions"]):
            return "adds_drops", params
            
        if any(term in query for term in ["draft", "drafting", "draft pick", "adp", "average draft position"]):
            return "draft_rankings", params
            
        if any(term in query for term in ["auction", "auction value", "budget", "price", "dollar value"]):
            return "auction_values", params
            
        if any(term in query for term in ["tier", "tiers", "player tier", "grouping"]):
            return "player_tiers", params
            
        if any(term in query for term in ["dynasty", "keeper", "multi-year", "long-term"]):
            return "dynasty", params
            
        if any(term in query for term in ["best ball", "bestball", "no lineup changes"]):
            return "bestball", params
            
        if any(term in query for term in ["bye", "bye week", "week off", "rest week"]):
            return "bye_weeks", params
            
        if any(term in query for term in ["defense", "defensive", "defense against position", "defense ranking"]):
            return "defense_rankings", params
            
        # Default to general query
        return "general", params

    async def _fetch_relevant_data(self, query_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fetch the relevant NFL data based on query type, combining multiple data sources when needed
        
        Args:
            query_type (str): Type of the query (player_rankings, matchups, etc.)
            params (dict): Parameters extracted from the query
            
        Returns:
            dict: Combined data from relevant endpoints
        """
        try:
            # Get the basic parameters from the params dict
            teams = params.get("teams", [])
            original_query = params.get("original_query", "")
            
            # Create a dict to store combined data
            combined_data = {
                "query_type": query_type,
            }
            
            # Fetch data based on query type with combined relevant sources
            if query_type == "player_rankings":
                # Get league structure for team context
                combined_data["league"] = await self.api_client.get_teams()
                
                # Get draft rankings for rankings context
                try:
                    # Determine format type from query
                    original_query = params.get("original_query", "").lower()
                    format_type = "std"  # default
                    if "ppr" in original_query:
                        format_type = "ppr"
                    elif "half" in original_query:
                        format_type = "half"
                    elif "superflex" in original_query or "2qb" in original_query:
                        format_type = "superflex"
                    
                    combined_data["draft_rankings"] = await self.api_client.get_draft_rankings(format_type)
                    
                    # Add metadata about which player we're looking for
                    player_name = params.get("player")
                    if player_name:
                        combined_data["metadata"] = {"target_player": player_name}
                        
                        # Check if the player_name is found in the rankings and add direct reference
                        draft_rankings = combined_data.get("draft_rankings", [])
                        if isinstance(draft_rankings, list):
                            player_found = False
                            for player in draft_rankings:
                                # Check various name fields that might exist in the data
                                player_display_name = player.get("display_name", "").lower()
                                player_name_field = player.get("name", "").lower()
                                if (player_name.lower() in player_display_name or 
                                    player_name.lower() in player_name_field):
                                    combined_data["target_player_data"] = player
                                    player_found = True
                                    break
                            
                            if not player_found:
                                combined_data["metadata"]["player_found"] = False
                        
                except Exception as e:
                    print(f"Error fetching draft rankings: {e}")
                
                # Get weekly rankings for additional context
                try:
                    combined_data["weekly_rankings"] = await self.api_client.get_weekly_rankings()
                except Exception as e:
                    print(f"Error fetching weekly rankings: {e}")
                
                # Add ADP data for additional ranking context
                try:
                    combined_data["adp"] = await self.api_client.get_adp(format=format_type)
                except Exception as e:
                    print(f"Error fetching ADP data: {e}")
                
                # If a specific player is mentioned, get their detailed information
                player_name = params.get("player")
                if player_name:
                    try:
                        from App.services.nfl_service import nfl_service
                        player_details = await nfl_service.get_player_detailed_info(player_name, include_inactive=False)
                        combined_data["player_details"] = player_details
                        print(f"DEBUG: Retrieved player details for {player_name} in player_rankings")
                    except Exception as e:
                        print(f"Error fetching player details in player_rankings: {e}")
                        combined_data["player_details"] = {"error": f"Could not fetch player details: {str(e)}"}
                
            elif query_type == "player_search":
                # Comprehensive player search across multiple endpoints
                player_name = params.get("player")
                if player_name:
                    combined_data["metadata"] = {"target_player": player_name, "search_type": "comprehensive"}
                    
                    # Get detailed player information from NFL players endpoint
                    try:
                        from App.services.nfl_service import nfl_service
                        player_details = await nfl_service.get_player_detailed_info(player_name, include_inactive=False)
                        combined_data["player_details"] = player_details
                        print(f"DEBUG: Retrieved player details for {player_name}")
                    except Exception as e:
                        print(f"Error fetching player details: {e}")
                        combined_data["player_details"] = {"error": f"Could not fetch player details: {str(e)}"}
                    
                    # Check draft projections first
                    try:
                        combined_data["draft_projections"] = await self.api_client.get_draft_projections()
                    except Exception as e:
                        print(f"Error fetching draft projections: {e}")
                    
                    # Check draft rankings
                    try:
                        combined_data["draft_rankings"] = await self.api_client.get_draft_rankings("std")
                    except Exception as e:
                        print(f"Error fetching draft rankings: {e}")
                    
                    # Check weekly rankings
                    try:
                        combined_data["weekly_rankings"] = await self.api_client.get_weekly_rankings()
                    except Exception as e:
                        print(f"Error fetching weekly rankings: {e}")
                    
                    # Check ROS projections
                    try:
                        combined_data["ros_projections"] = await self.api_client.get_rest_of_season_projections()
                    except Exception as e:
                        print(f"Error fetching ROS projections: {e}")
                    
                    # Get league structure for team context
                    combined_data["league"] = await self.api_client.get_teams()
                else:
                    # Fallback to general query if no player specified
                    combined_data["league"] = await self.api_client.get_teams()
                    combined_data["standings"] = await self.api_client.get_standings()
                
            elif query_type == "matchups":
                # Get schedule data
                combined_data["schedule"] = await self.api_client.get_schedule()
                  # If specific teams mentioned, filter or highlight their games
                if teams:
                    relevant_games = []
                    # Handle both possible data structures
                    schedule_games = combined_data.get("schedule", {}).get("schedule", [])
                    if not schedule_games:
                        schedule_games = combined_data.get("schedule", {}).get("games", [])
                    
                    for game in schedule_games:
                        # Handle direct team fields (current API structure)
                        home_team = game.get("home_team", "")
                        away_team = game.get("away_team", "")
                        
                        # Handle nested structure (fallback)
                        if not home_team:
                            home_team = game.get("home", {}).get("alias", "")
                        if not away_team:
                            away_team = game.get("away", {}).get("alias", "")
                            
                        if home_team in teams or away_team in teams:
                            relevant_games.append(game)
                    combined_data["relevant_games"] = relevant_games
                
            elif query_type == "injuries":
                # Get injury data
                try:
                    combined_data["injuries"] = await self.api_client.get_weekly_injuries()
                except Exception as e:
                    print(f"Error fetching injuries: {e}")
                
                # Get team context
                combined_data["league"] = await self.api_client.get_teams()
                
                # Add news data which may contain injury updates
                try:
                    combined_data["news"] = await self.api_client.get_nfl_news()
                except Exception as e:
                    print(f"Error fetching news: {e}")
                
                # If specific teams mentioned, highlight their injuries
                if teams:
                    team_injuries = {}
                    injury_data = combined_data.get("injuries", {})
                    for team in injury_data.get("teams", []):
                        if team.get("alias") in teams:
                            team_injuries[team.get("alias")] = team
                    combined_data["team_injuries"] = team_injuries
                
            elif query_type == "schedule":
                # Get the full schedule
                combined_data["schedule"] = await self.api_client.get_schedule()
                
                # Get team context
                combined_data["league"] = await self.api_client.get_teams()                  # If specific teams mentioned, filter their games
                if teams:
                    team_games = {}
                    for team_code in teams:
                        team_games[team_code] = []
                        
                    # Handle both possible data structures
                    schedule_games = combined_data.get("schedule", {}).get("schedule", [])
                    if not schedule_games:
                        schedule_games = combined_data.get("schedule", {}).get("games", [])
                    
                    for game in schedule_games:
                        # Handle direct team fields (current API structure)
                        home_team = game.get("home_team", "")
                        away_team = game.get("away_team", "")
                        
                        # Handle nested structure (fallback)
                        if not home_team:
                            home_team = game.get("home", {}).get("alias", "")
                        if not away_team:
                            away_team = game.get("away", {}).get("alias", "")
                            
                        for team_code in teams:
                            if home_team == team_code or away_team == team_code:
                                team_games[team_code].append(game)
                                
                    combined_data["team_games"] = team_games
                
            elif query_type == "depth_chart":
                # For depth charts, we need the full depth charts data
                try:
                    combined_data["depth_charts"] = await self.api_client.get_depth_charts()
                except Exception as e:
                    print(f"Error fetching depth charts: {e}")
                
                # Also get teams information for context
                combined_data["league"] = await self.api_client.get_teams()
                
            elif query_type == "standings":
                # Get standings data
                combined_data["standings"] = await self.api_client.get_standings()
                  # Get team context
                combined_data["league"] = await self.api_client.get_teams()
                
            elif query_type == "draft_rankings":
                # Get draft rankings
                format_type = "std"  # default
                original_query = params.get("original_query", "").lower()
                if "ppr" in original_query:
                    format_type = "ppr"
                elif "half" in original_query:
                    format_type = "half"
                elif "superflex" in original_query or "2qb" in original_query:
                    format_type = "superflex"
                    
                combined_data["draft_rankings"] = await self.api_client.get_draft_rankings(format_type)
                combined_data["adp"] = await self.api_client.get_adp(format=format_type)
                
            elif query_type == "draft_projections":
                # Get draft projections
                combined_data["draft_projections"] = await self.api_client.get_draft_projections()
                # Also get league structure for team context
                combined_data["league"] = await self.api_client.get_teams()
                
            elif query_type == "auction_values":
                # Get auction values
                original_query = params.get("original_query", "").lower()
                format_type = "std"
                if "ppr" in original_query:
                    format_type = "ppr"
                
                teams = 12  # default
                teams_match = re.search(r'(\d+)\s*teams?', original_query)
                if teams_match:
                    teams_num = int(teams_match.group(1))
                    if teams_num in [8, 10, 12, 14, 16]:
                        teams = teams_num
                
                budget = 200  # default
                budget_match = re.search(r'(\d+)\s*(?:dollars|budget)', original_query)
                if budget_match:
                    budget = int(budget_match.group(1))
                    
                combined_data["auction_values"] = await self.api_client.get_auction_values(teams, budget, format_type)
                
            elif query_type == "player_tiers":
                # Get player tiers
                original_query = params.get("original_query", "").lower()
                format_type = "std"
                if "ppr" in original_query:
                    format_type = "ppr"
                    
                combined_data["player_tiers"] = await self.api_client.get_player_tiers(format_type)
                
            elif query_type == "dynasty":
                # Get dynasty rankings
                combined_data["dynasty_rankings"] = await self.api_client.get_dynasty_rankings()
                
            elif query_type == "bestball":
                # Get best ball rankings
                combined_data["bestball_rankings"] = await self.api_client.get_best_ball_rankings()
                
            elif query_type == "bye_weeks":
                # Get bye weeks
                combined_data["bye_weeks"] = await self.api_client.get_bye_weeks()
                
            elif query_type == "defense_rankings":
                # Get defensive rankings
                combined_data["defensive_rankings"] = await self.api_client.get_defensive_rankings()
                
            elif query_type == "weather":
                # Get weather forecasts
                combined_data["weather_forecasts"] = await self.api_client.get_weather_forecasts()
                
                # Get teams and schedule for context
                combined_data["league"] = await self.api_client.get_teams()
                combined_data["schedule"] = await self.api_client.get_schedule()
            
            elif query_type == "adds_drops":
                # Get player adds and drops
                combined_data["adds_drops"] = await self.api_client.get_player_adds_drops()
                
                # Get additional context
                combined_data["league"] = await self.api_client.get_teams()
            
            elif query_type == "ros_projections":
                # Get rest of season projections
                combined_data["ros_projections"] = await self.api_client.get_rest_of_season_projections()
                
                # Get additional context for comparison
                try:
                    combined_data["weekly_rankings"] = await self.api_client.get_weekly_rankings()
                except Exception as e:
                    print(f"Error fetching weekly rankings: {e}")
                
                # If a specific player is mentioned, get their detailed information
                player_name = params.get("player")
                if player_name:
                    try:
                        from App.services.nfl_service import nfl_service
                        player_details = await nfl_service.get_player_detailed_info(player_name, include_inactive=False)
                        combined_data["player_details"] = player_details
                        print(f"DEBUG: Retrieved player details for {player_name} in ros_projections")
                    except Exception as e:
                        print(f"Error fetching player details in ros_projections: {e}")
                        combined_data["player_details"] = {"error": f"Could not fetch player details: {str(e)}"}
                    
            else:  # General query
                # For general queries, provide league structure and standings
                combined_data["league"] = await self.api_client.get_teams()
                combined_data["standings"] = await self.api_client.get_standings()
                
                # Add current week's schedule
                combined_data["schedule"] = await self.api_client.get_schedule()
                
                # Add weekly rankings and projections
                try:
                    combined_data["weekly_rankings"] = await self.api_client.get_weekly_rankings()
                except Exception as e:
                    print(f"Error fetching weekly rankings: {e}")
            
            return combined_data
            
        except Exception as e:
            print(f"Error fetching relevant data: {e}")
            return {"error": str(e), "query_type": query_type}
        
    def get_data_sources(self, query_type):
        """
        Return information about data sources used, with specific API endpoints
        
        Args:
            query_type (str): The type of query being processed
            
        Returns:
            list: A list of API endpoints that were used as data sources
        """
        # Map query types to the actual Fantasy Nerds API endpoints used
        data_sources = {
            "player_rankings": ["/nfl/teams", "/nfl/draft-rankings", "/nfl/weekly-rankings"],
            "player_search": ["/nfl/draft-projections", "/nfl/draft-rankings", "/nfl/weekly-rankings", "/nfl/ros", "/nfl/teams"],
            "matchups": ["/nfl/schedule", "/nfl/teams"],
            "injuries": ["/nfl/injuries", "/nfl/teams", "/nfl/news"],
            "schedule": ["/nfl/schedule", "/nfl/teams"],
            "depth_chart": ["/nfl/depth", "/nfl/teams"],
            "standings": ["/nfl/standings", "/nfl/teams"],            "draft_rankings": ["/nfl/draft-rankings", "/nfl/adp"],
            "draft_projections": ["/nfl/draft-projections", "/nfl/teams"],
            "auction_values": ["/nfl/auction-values"],
            "player_tiers": ["/nfl/player-tiers"],
            "dynasty": ["/nfl/dynasty"],
            "bestball": ["/nfl/bestball"],
            "bye_weeks": ["/nfl/bye-weeks"],
            "defense_rankings": ["/nfl/defense-rankings"],
            "weather": ["/nfl/weather", "/nfl/schedule", "/nfl/teams"],
            "adds_drops": ["/nfl/add-drops", "/nfl/teams"],
            "ros_projections": ["/nfl/ros", "/nfl/weekly-rankings"],
            "general": ["/nfl/teams", "/nfl/schedule", "/nfl/standings"]
        }
        
        # Ensure we always return a list, even if the query type isn't recognized
        sources = data_sources.get(query_type)
        if sources is None or not isinstance(sources, list) or len(sources) == 0:
            return ["Fantasy Nerds NFL API Data"]
        return sources

nfl_query_service = NFLQueryService()
