"""
Scryfall API integration for getting Magic: The Gathering card information
"""
import json
import requests
import time
from pathlib import Path
from typing import Dict, Optional, List, Union
import hashlib
import logging

# Configure basic logging for the package so INFO messages are visible by default
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mtg_agent.scryfall")


class ScryfallCache:
    """Manages Scryfall card cache"""
    
    def __init__(self, cache_dir: str = "scryfall_cache"):
        self.cache_dir = Path(__file__).parent.parent / cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        self.session = requests.Session()
        # Scryfall recommends waiting at least 50-100ms between requests
        self.request_delay = 0.1
        self.last_request_time = 0
    
    def _get_cache_filename(self, card_name: str) -> Path:
        """Generate a safe filename for cache"""
        # Create hash of name to avoid issues with special characters
        name_hash = hashlib.md5(card_name.lower().encode()).hexdigest()
        safe_name = "".join(c for c in card_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        return self.cache_dir / f"{safe_name}_{name_hash}.json"
    
    def _wait_for_rate_limit(self):
        """Respect Scryfall rate limit"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.request_delay:
            time.sleep(self.request_delay - time_since_last)
        self.last_request_time = time.time()
    
    def get_card_info(self, card_name: str) -> Optional[Dict]:
        """Get card information, using cache if available"""
        cache_file = self._get_cache_filename(card_name)
        
        # Try to load from cache
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"📥 Cargado desde caché: {card_name} -> {cache_file}")
                return data
            except Exception as e:
                logger.warning(f"⚠️ Error reading cache for {card_name}: {e}")

        # If not in cache, make request to Scryfall
        return self._fetch_from_scryfall(card_name, cache_file)
    
    def _fetch_from_scryfall(self, card_name: str, cache_file: Path) -> Optional[Dict]:
        """Make request to Scryfall and save to cache"""
        try:
            self._wait_for_rate_limit()
            
            # Use Scryfall exact search API
            url = "https://api.scryfall.com/cards/named"
            params = {"exact": card_name}
            
            response = self.session.get(url, params=params)
            
            if response.status_code == 200:
                card_data = response.json()
                
                # Save to cache
                try:
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(card_data, f, indent=2, ensure_ascii=False)
                    logger.info(f"💾 Guardado en caché: {cache_file}")
                except Exception as e:
                    logger.warning(f"⚠️ Error guardando caché para {card_name}: {e}")

                logger.info(f"✅ Retrieved information from Scryfall: {card_name} (cached: {cache_file})")
                return card_data
            
            elif response.status_code == 404:
                logger.warning(f"⚠️ Card not found in Scryfall: {card_name}")
                return None
            
            else:
                logger.error(f"❌ Error {response.status_code} getting {card_name}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Connection error getting {card_name}: {e}")
            return None
    
    def get_mana_cost(self, card_name: str) -> Optional[str]:
        """Get the mana cost of a card"""
        card_info = self.get_card_info(card_name)
        if card_info:
            return card_info.get('mana_cost', '')
        return None
    
    def get_cmc(self, card_name: str) -> Optional[int]:
        """Get the converted mana cost (CMC) of a card"""
        card_info = self.get_card_info(card_name)
        if card_info:
            return card_info.get('cmc', 0)
        return None
    
    def get_type_line(self, card_name: str) -> Optional[str]:
        """Get the type line of a card"""
        card_info = self.get_card_info(card_name)
        if card_info:
            return card_info.get('type_line', '')
        return None

    def download_card_image(self, card_name: str, dest_dir: str | None = None) -> Optional[Path]:
        """Download the card image for a card and save it to an image cache directory.

        This method will look for image URIs in the card JSON (single-faced or multi-faced cards)
        and attempt to download the first available image. It will not overwrite existing files.
        Returns the Path to the saved image or None on failure.
        """
        card_info = self.get_card_info(card_name)
        if not card_info:
            logger.error(f"❌ No se puede descargar imagen - no hay información de la carta: {card_name}")
            return None

        image_uri = None
        # Single-faced card
        if isinstance(card_info.get('image_uris'), dict):
            image_uris = card_info['image_uris']
            # Prefer large, then normal, then png, else first
            image_uri = image_uris.get('large') or image_uris.get('normal') or image_uris.get('png') or next(iter(image_uris.values()))
        # Multi-faced card
        elif isinstance(card_info.get('card_faces'), list):
            for face in card_info['card_faces']:
                if isinstance(face.get('image_uris'), dict):
                    image_uris = face['image_uris']
                    image_uri = image_uris.get('large') or image_uris.get('normal') or image_uris.get('png')
                    if image_uri:
                        break

        if not image_uri:
            logger.warning(f"⚠️ No se encontró imagen para: {card_name}")
            return None

        dest_dir_path = Path(__file__).parent.parent / (dest_dir or 'image_cache')
        dest_dir_path.mkdir(exist_ok=True)

        # Create a safe filename using the card name
        ext = Path(image_uri.split('?')[0]).suffix or '.png'
        safe_name = "".join(c for c in card_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = dest_dir_path / f"{safe_name}{ext}"

        if filename.exists():
            logger.info(f"🖼️ Imagen ya en caché: {filename}")
            return filename

        try:
            logger.info(f"⬇️ Descargando imagen: {card_name} -> {filename}")
            resp = self.session.get(image_uri, stream=True, timeout=15)
            if resp.status_code == 200:
                with open(filename, 'wb') as f:
                    for chunk in resp.iter_content(1024):
                        f.write(chunk)
                logger.info(f"💾 Imagen guardada: {filename}")
                return filename
            else:
                logger.error(f"❌ Error descargando imagen ({resp.status_code}): {image_uri}")
                return None
        except Exception as e:
            logger.error(f"❌ Excepción descargando imagen {card_name}: {e}")
            return None


class ManaCurveCalculator:
    """Calculates the mana curve of a deck"""
    
    def __init__(self, scryfall_cache: ScryfallCache):
        self.cache = scryfall_cache
        # Directory for mana curve cache files (one per deck hash)
        self.cache_dir = Path(__file__).parent.parent / ".cache"
        self.cache_dir.mkdir(exist_ok=True)
    
    def calculate_mana_curve(self, deck_lines: List[str]) -> Dict:
        """Calculate the mana curve of the deck"""
        # Compute deck hash to allow caching of the result when the deck doesn't change
        deck_hash = self._deck_hash(deck_lines)

        # Try load from cache first
        cached = self._load_cached_curve(deck_hash)
        if cached is not None:
            # Mark that this result was loaded from cache (optional)
            cached['_cached'] = True
            return cached

        curve: Dict[Union[int, str], int] = dict.fromkeys(range(0, 8), 0)
        curve['7+'] = 0
        
        stats = {
            'total_cards': 0,
            'lands': 0,
            'nonlands': 0,
            'commander_cmc': 0,
            'failed_cards': []
        }
        
        # Process each deck line
        for i, line in enumerate(deck_lines):
            card_data = self._process_deck_line(line, i == len(deck_lines) - 1)
            if not card_data:
                continue
            
            quantity, card_name, is_commander = card_data
            self._update_curve_stats(curve, stats, quantity, card_name, is_commander)
        
        stats['average_cmc'] = self._calculate_average_cmc(curve, stats['nonlands'])
        result = {
            'curve': curve,
            **stats
        }

        # Save to cache for future calls
        try:
            self._save_cached_curve(deck_hash, result)
        except Exception:
            # If cache saving fails, don't break the calculation
            pass

        return result

    def _deck_hash(self, deck_lines: List[str]) -> str:
        """Return an MD5 hash for the deck content (order and whitespace sensitive)."""
        joined = "\n".join([line.strip() for line in deck_lines if line is not None])
        return hashlib.md5(joined.encode('utf-8')).hexdigest()

    def _get_cache_filepath(self, deck_hash: str) -> Path:
        """Get path for cached mana curve for a given deck hash."""
        return self.cache_dir / f"mana_curve_{deck_hash}.json"

    def _load_cached_curve(self, deck_hash: str) -> Optional[Dict]:
        """Load cached curve data if available and return it, otherwise None."""
        path = self._get_cache_filepath(deck_hash)
        if not path.exists():
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ Error reading mana curve cache {path}: {e}")
            return None

    def _save_cached_curve(self, deck_hash: str, data: Dict):
        """Save curve data to cache file for the given deck hash."""
        path = self._get_cache_filepath(deck_hash)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"💾 Mana curve guardada en caché: {path}")
        except Exception as e:
            logger.warning(f"⚠️ Error saving mana curve cache {path}: {e}")

    def _process_deck_line(self, line: str, is_last_line: bool):
        """Process a deck line and return basic data"""
        line = line.strip()
        if not line:
            return None
        
        parts = line.split(' ', 1)
        if len(parts) != 2:
            return None
        
        try:
            quantity = int(parts[0])
            card_name = parts[1]
            return quantity, card_name, is_last_line
        except ValueError:
            return None
    
    def _update_curve_stats(self, curve, stats, quantity: int, card_name: str, is_commander: bool):
        """Update curve statistics with a card"""
        cmc = self.cache.get_cmc(card_name)
        type_line = self.cache.get_type_line(card_name)
        
        if cmc is None:
            stats['failed_cards'].append(card_name)
            return
        
        is_land = type_line and 'Land' in type_line if type_line else False
        
        if is_commander:
            stats['commander_cmc'] = cmc
        elif is_land:
            stats['lands'] += quantity
        else:
            stats['nonlands'] += quantity
            # Add to mana curve
            if cmc >= 7:
                curve['7+'] += quantity
            else:
                curve[cmc] += quantity
        
        stats['total_cards'] += quantity
    
    def _calculate_average_cmc(self, curve: Dict[Union[int, str], int], total_nonlands: int) -> float:
        """Calculate the average CMC of non-land cards"""
        if total_nonlands == 0:
            return 0.0
        
        total_cmc = 0
        for cmc, count in curve.items():
            if cmc == '7+':
                total_cmc += 7 * count  # Use 7 as approximation for 7+
            elif isinstance(cmc, int):
                total_cmc += cmc * count
        
        return total_cmc / total_nonlands if total_nonlands > 0 else 0.0
    
    def format_mana_curve(self, curve_data: Dict) -> str:
        """Format mana curve for display to user"""
        curve = curve_data['curve']
        
        result = "📊 **MANA CURVE**\n"
        result += f"• Lands: {curve_data['lands']}\n"
        result += f"• Spells: {curve_data['nonlands']}\n"
        result += f"• Average CMC: {curve_data['average_cmc']:.1f}\n"
        result += f"• Commander (CMC {curve_data['commander_cmc']})\n\n"
        
        # Show distribution by CMC
        result += "**Distribution by CMC:**\n"
        for cmc in range(0, 8):
            count = curve.get(cmc, 0)
            if count > 0:
                bar = "█" * min(count, 20)  # Limit bar to 20 characters
                result += f"• {cmc}: {count:2d} {bar}\n"
        
        # CMC 7+
        count_7plus = curve.get('7+', 0)
        if count_7plus > 0:
            bar = "█" * min(count_7plus, 20)
            result += f"• 7+: {count_7plus:2d} {bar}\n"
        
        # Show failed cards
        if curve_data['failed_cards']:
            result += f"\n⚠️ **Cards not found in Scryfall:** {len(curve_data['failed_cards'])}\n"
            for card in curve_data['failed_cards'][:5]:  # Show only first 5
                result += f"• {card}\n"
            if len(curve_data['failed_cards']) > 5:
                result += f"• ... and {len(curve_data['failed_cards']) - 5} more\n"
        
        return result


# Global cache instance
scryfall_cache = ScryfallCache()
mana_curve_calculator = ManaCurveCalculator(scryfall_cache)