import asyncio
import logging

logger = logging.getLogger("astrbot")

async def fetch_org_members(
    symbol: str = "GFHB",
    pagesize: int = 32,
    sleep_seconds: float = 0.2,
    max_pages: int | None = None,
):
    import aiohttp
    from bs4 import BeautifulSoup

    url = "https://robertsspaceindustries.com/api/orgs/getOrgMembers"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json",
        "Origin": "https://robertsspaceindustries.com",
        "Referer": f"https://robertsspaceindustries.com/en/orgs/{symbol}/members"
    }

    members = []
    page = 1
    
    async with aiohttp.ClientSession() as session:
        while True:
            payload = {
                "symbol": symbol,
                "search": "",
                "pagesize": pagesize,
                "page": page
            }
            
            try:
                async with session.post(url, json=payload, headers=headers, timeout=15) as resp:
                    if resp.status != 200:
                        logger.error(f"[RSI Scraper] HTTP Error {resp.status} on page {page}")
                        break
                        
                    data = await resp.json()
                    
                    if data.get("success") != 1 or not data.get("data") or not data["data"].get("html"):
                        logger.warning(f"[RSI Scraper] API returned unsuccessful or empty HTML on page {page}")
                        break
                        
                    html = data["data"]["html"]
                    soup = BeautifulSoup(html, "html.parser")
                    
                    # The HTML usually contains multiple <li class="member-item">
                    member_items = soup.find_all("li", class_="member-item")
                    if not member_items:
                        break # No more members
                        
                    for item in member_items:
                        # Extract Moniker and Handle
                        # Structure is usually: <span class="name">Moniker</span> <span class="nick">Handle</span>
                        name_span = item.find("span", class_="name")
                        nick_span = item.find("span", class_="nick")
                        
                        # Extract Rank and Role
                        # Structure is usually <span class="rank">Rank</span> or <span class="role">Role</span>
                        # Let's extract the title or info section
                        info_div = item.find("div", class_="info")
                        
                        moniker = name_span.text.strip() if name_span else ""
                        handle = nick_span.text.strip() if nick_span else ""
                        
                        # Extract Rank (usually the rank level like 正式成员, 舰长, etc.)
                        rank_span = item.find("span", class_="rank")
                        rank_text = rank_span.text.strip() if rank_span else ""
                        
                        # Extract roles from rolelist (like 委员会)
                        rolelist_ul = item.find("ul", class_="rolelist")
                        roles = []
                        if rolelist_ul:
                            role_lis = rolelist_ul.find_all("li", class_="role")
                            roles = [li.text.strip() for li in role_lis]
                            
                        # If the rank is something significant (like 舰长), we should prioritize it.
                        # Sometimes roles is just "委员会" but rank is "舰长". 
                        # We combine them if they are different and both exist, or use rank if it's significant.
                        significant_ranks = ["founder", "director", "officer", "leader", "boss", "admin", "舰长", "副舰长"]
                        is_rank_significant = any(k in rank_text.lower() for k in significant_ranks)
                        
                        if is_rank_significant:
                            display_role = rank_text
                            if roles and roles[0] != rank_text:
                                display_role += f" ({', '.join(roles)})"
                        else:
                            # If rank is just normal, use roles if available, otherwise fallback to rank
                            display_role = ", ".join(roles) if roles else rank_text
                        
                        # Check for hidden members
                        # Usually hidden members don't have a nick/handle, or they have specific classes
                        is_hidden = False
                        # If both moniker and handle are 'Unknown' or empty, it's definitely a hidden member
                        if (not moniker or moniker == "Unknown") and (not handle or handle == "Unknown"):
                            is_hidden = True
                        elif not nick_span and not name_span:
                            is_hidden = True
                        elif "Redacted" in moniker or "Redacted" in handle:
                            is_hidden = True
                        
                        # stars or rank level
                        # E.g. <span class="stars" style="width: 100%;"></span> -> 100% means 5 stars
                        stars_span = item.find("span", class_="stars")
                        stars_count = 0
                        if stars_span and stars_span.has_attr("style"):
                            style_str = stars_span["style"]
                            # extract percentage, e.g. "width: 100%;"
                            if "width" in style_str:
                                try:
                                    percent_str = style_str.split("width:")[1].split("%")[0].strip()
                                    percent = int(percent_str)
                                    stars_count = int(percent / 20)
                                except:
                                    pass
                            
                        # Status color logic: 
                        # black = normal member (正式成员)
                        # blue = higher than normal, lower than committee (e.g. 高级成员, 教官, etc.)
                        # red = committee and above (e.g. 委员会, 舰长, Founder, etc.)
                        color_level = "black"
                        rank_weight = 3 # 1=red(top), 2=blue(mid), 3=black(normal), 4=hidden(bottom)
                        
                        lower_role = display_role.lower()
                        red_keywords = ["founder", "director", "officer", "leader", "boss", "admin", "舰长", "委员会"]
                        normal_keywords = ["正式成员", "affiliate", ""]
                        
                        # Use exact match or keyword match for normal members
                        is_normal = False
                        if display_role in ["正式成员", "Affiliate", ""]:
                            is_normal = True
                            
                        if any(k in lower_role for k in red_keywords) or stars_count >= 4:
                            color_level = "red"
                            rank_weight = 1
                        elif not is_normal:
                            color_level = "blue"
                            rank_weight = 2
                            
                        if is_hidden:
                            handle = ""
                            moniker = ""
                            rank_weight = 4
                            
                        members.append({
                            "handle": handle,
                            "moniker": moniker,
                            "rank": display_role,
                            "stars": stars_count,
                            "color_level": color_level,
                            "rank_weight": rank_weight,
                            "is_hidden": is_hidden
                        })
                    
                    page += 1
                    if max_pages is not None and page > max_pages:
                        break
                    if sleep_seconds > 0:
                        await asyncio.sleep(sleep_seconds)
                    
            except Exception as e:
                logger.error(f"[RSI Scraper] Error on page {page}: {e}")
                break
                
    # Separate hidden and visible members to ensure perfect sorting
    visible_members = [m for m in members if not m["is_hidden"]]
    hidden_members = [m for m in members if m["is_hidden"]]
    
    # Sort visible members strictly by handle alphabetically
    visible_members.sort(key=lambda x: x["handle"].lower())
    
    # Hidden members have no handle, just append them at the very end
    final_members = visible_members + hidden_members
    
    return final_members
