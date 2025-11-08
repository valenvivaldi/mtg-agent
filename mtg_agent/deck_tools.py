"""
Tools for manipulating Magic: The Gathering decks
"""
import os
from pathlib import Path
from langchain_core.tools import tool
from .scryfall_integration import scryfall_cache

# Constant for the deck filename
DECK_FILENAME = "deck.txt"


def _get_deck_file_path() -> Path:
    """Get the path to the deck.txt file"""
    project_root = Path(__file__).parent.parent
    return project_root / DECK_FILENAME


def _read_deck_lines():
    """Read lines from the deck.txt file"""
    deck_file = _get_deck_file_path()
    if not deck_file.exists():
        raise FileNotFoundError(f"Deck file {DECK_FILENAME} not found at {deck_file}")
    
    with open(deck_file, 'r', encoding='utf-8') as f:
        return f.readlines()


def _parse_card_line(line: str):
    """Parse a deck line and return (quantity, card_name) or None if invalid"""
    line = line.strip()
    if not line:
        return None
    
    parts = line.split(' ', 1)
    if len(parts) != 2:
        return None
    
    try:
        quantity = int(parts[0])
        card_name = parts[1]
        return quantity, card_name
    except ValueError:
        return None


def _write_deck_lines(lines):
    """Write lines to the deck.txt file"""
    deck_file = _get_deck_file_path()
    with open(deck_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)


@tool
def modify_deck_card(card_name: str, quantity_change: int) -> str:
    """
    Modify the quantity of a card in the deck.
    
    Args:
        card_name: Exact name of the card to modify
        quantity_change: Amount to add (positive) or subtract (negative) from the card
        
    Returns:
        Message indicating the result of the operation
    """
    try:
        lines = _read_deck_lines()
        
        # Separate commander from the rest of the deck
        commander_line = lines[-1] if lines and lines[-1].strip() else None
        deck_lines = lines[:-2] if len(lines) > 1 else []
        
        new_lines, result_msg = _process_deck_modification(deck_lines, card_name, quantity_change)
        
        # Add empty line and commander at the end
        if commander_line:
            new_lines.append('\n')
            new_lines.append(commander_line)
        
        _write_deck_lines(new_lines)
        return result_msg
        
    except FileNotFoundError as e:
        return f"❌ Error: {str(e)}"
    except Exception as e:
        return f"❌ Error modifying deck: {str(e)}"


def _process_deck_modification(deck_lines, card_name: str, quantity_change: int):
    """Process the modification of a card in the deck"""
    new_lines = []
    card_found = False
    
    for line in deck_lines:
        if not line.strip():
            new_lines.append(line)
            continue
            
        parsed = _parse_card_line(line)
        if not parsed:
            new_lines.append(line)
            continue
            
        current_quantity, current_card_name = parsed
        
        if current_card_name.lower() == card_name.lower():
            card_found = True
            new_quantity = current_quantity + quantity_change
            result_msg = _handle_card_modification(new_lines, current_card_name, current_quantity, new_quantity)
        else:
            new_lines.append(line)
    
    # Handle card not found
    if not card_found:
        result_msg = _handle_card_not_found(new_lines, card_name, quantity_change)
    
    return new_lines, result_msg


def _handle_card_modification(new_lines, card_name: str, old_quantity: int, new_quantity: int):
    """Handle modification of an existing card"""
    if new_quantity > 0:
        new_lines.append(f"{new_quantity} {card_name}\n")
        return f"✅ {card_name}: {old_quantity} → {new_quantity}"
    else:
        return f"🗑️ {card_name} removed from deck (quantity: {old_quantity} → 0)"


def _handle_card_not_found(new_lines, card_name: str, quantity_change: int):
    """Handle the case when a card is not found in the deck"""
    if quantity_change > 0:
        new_lines.append(f"{quantity_change} {card_name}\n")
        return f"➕ {card_name} added to deck (quantity: {quantity_change})"
    else:
        return f"❌ Error: Card '{card_name}' not found in deck"


@tool
def view_deck() -> str:
    """
    Show the current deck content.
    
    Returns:
        Complete deck content or error message
    """
    try:
        deck_file = _get_deck_file_path()
        with open(deck_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Calculate basic statistics
        lines = content.strip().split('\n')
        total_cards, commander = _count_deck_cards(lines)
        
        result = f"📋 **CURRENT DECK** (Total: {total_cards} cards)\n"
        result += f"Commander: {commander}\n\n"
        result += content
        
        return result
        
    except FileNotFoundError as e:
        return f"❌ Error: {str(e)}"
    except Exception as e:
        return f"❌ Error reading deck: {str(e)}"


def _count_deck_cards(lines):
    """Count deck cards and find the commander"""
    total_cards = 0
    commander = None
    
    for line in lines:
        parsed = _parse_card_line(line)
        if not parsed:
            continue
            
        quantity, card_name = parsed
        
        # The last non-empty card is the commander
        if line.strip() == lines[-1].strip():
            commander = card_name
        else:
            total_cards += quantity
    
    # Add commander to total (always 1)
    if commander:
        total_cards += 1
    
    return total_cards, commander


@tool
def get_card_info(card_name: str) -> str:
    """
    Get detailed information about a specific card from Scryfall.
    
    Args:
        card_name: Exact name of the card
        
    Returns:
        Detailed card information or error message
    """
    try:
        card_info = scryfall_cache.get_card_info(card_name)
        
        if not card_info:
            return f"❌ Card information not found: {card_name}"
        
        # Extract relevant information
        name = card_info.get('name', 'N/A')
        mana_cost = card_info.get('mana_cost', 'N/A')
        cmc = card_info.get('cmc', 'N/A')
        type_line = card_info.get('type_line', 'N/A')
        oracle_text = card_info.get('oracle_text', 'N/A')
        power = card_info.get('power', '')
        toughness = card_info.get('toughness', '')
        
        result = f"🃏 **{name}**\n"
        result += f"• Mana Cost: {mana_cost}\n"
        result += f"• CMC: {cmc}\n"
        result += f"• Type: {type_line}\n"
        
        if power and toughness:
            result += f"• Power/Toughness: {power}/{toughness}\n"
        
        result += f"• Text: {oracle_text}\n"
        
        return result
        
    except Exception as e:
        return f"❌ Error getting information for {card_name}: {str(e)}"


@tool
def refresh_card_cache(card_name: str) -> str:
    """
    Refresh cached information for a specific card from Scryfall.
    
    Args:
        card_name: Exact name of the card to refresh
        
    Returns:
        Message indicating the refresh result
    """
    try:
        # Get cache file path
        cache_file = scryfall_cache._get_cache_filename(card_name)
        
        # Delete cache file if it exists
        if cache_file.exists():
            cache_file.unlink()
        
        # Get updated information
        card_info = scryfall_cache.get_card_info(card_name)
        
        if card_info:
            return f"✅ Information updated for: {card_name}"
        else:
            return f"❌ Could not get updated information for: {card_name}"
        
    except Exception as e:
        return f"❌ Error refreshing cache for {card_name}: {str(e)}"


@tool  
def get_deck_stats() -> str:
    """
    Get basic deck statistics.
    
    Returns:
        Deck statistics including card count and commander
    """
    try:
        lines = _read_deck_lines()
        stats = _calculate_deck_stats(lines)
        return _format_deck_stats(stats)
        
    except FileNotFoundError as e:
        return f"❌ Error: {str(e)}"
    except Exception as e:
        return f"❌ Error calculating statistics: {str(e)}"


def _calculate_deck_stats(lines):
    """Calculate basic deck statistics"""
    total_cards = 0
    unique_cards = 0
    commander = None
    card_counts = {}
    
    for line in lines:
        parsed = _parse_card_line(line)
        if not parsed:
            continue
            
        quantity, card_name = parsed
        
        # The last non-empty card is the commander
        if line.strip() == lines[-1].strip():
            commander = card_name
        else:
            total_cards += quantity
            unique_cards += 1
        
        card_counts[card_name] = quantity
    
    # Add commander to total
    if commander:
        total_cards += 1
        unique_cards += 1
    
    # Find cards with more than 1 copy
    multiple_copies = {name: count for name, count in card_counts.items() 
                      if count > 1 and name != commander}
    
    return {
        'total_cards': total_cards,
        'unique_cards': unique_cards,
        'commander': commander,
        'multiple_copies': multiple_copies
    }


def _format_deck_stats(stats):
    """Format statistics for display to user"""
    result = "📊 **DECK STATISTICS**\n"
    result += f"• Total cards: {stats['total_cards']}\n"
    result += f"• Unique cards: {stats['unique_cards']}\n"
    result += f"• Commander: {stats['commander']}\n"
    
    if stats['multiple_copies']:
        result += "\n🔢 **Cards with multiple copies:**\n"
        for card, count in sorted(stats['multiple_copies'].items()):
            result += f"• {card}: {count}x\n"
    else:
        result += "\n✅ All cards (except basic lands) are singleton\n"
    
    return result