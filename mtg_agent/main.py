import os  
from pathlib import Path
import uuid
import sys

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
# Import deck tools
from mtg_agent.deck_tools import modify_deck_card, view_deck, get_deck_stats, get_card_info, refresh_card_cache
from mtg_agent.scryfall_integration import mana_curve_calculator, scryfall_cache

def get_deck_content():
    """Read the content of deck.txt and return as string"""
    try:
        project_root = Path(__file__).parent.parent
        deck_file = project_root / "deck.txt"
        
        if deck_file.exists():
            with open(deck_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        else:
            return "Deck file deck.txt not found"
    except Exception as e:
        return f"Error reading deck.txt: {str(e)}"


def get_enhanced_deck_info():
    """Get complete deck information including mana curve"""
    try:
        project_root = Path(__file__).parent.parent
        deck_file = project_root / "deck.txt"
        
        if not deck_file.exists():
            return "Deck file deck.txt not found"
        
        # Read deck content
        with open(deck_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            lines = content.split('\n')

        # Calculate mana curve
        print("🔍 Calculating mana curve with Scryfall...")
        curve_data = mana_curve_calculator.calculate_mana_curve(lines)
        curve_text = mana_curve_calculator.format_mana_curve(curve_data)

        # Enrich each card line with mana cost and short oracle text (using cache)
        enriched_lines = []
        missing_cards = []
        for raw in lines:
            raw_strip = raw.strip()
            if not raw_strip:
                continue
            parts = raw_strip.split(' ', 1)
            if len(parts) != 2:
                enriched_lines.append(raw_strip)
                continue
            qty = parts[0]
            name = parts[1]

            card_info = scryfall_cache.get_card_info(name)
            if not card_info:
                missing_cards.append(name)
                enriched_lines.append(f"{qty} {name} (mana_cost: N/A) - Oracle: N/A")
                continue

            mana_cost = card_info.get('mana_cost', '')
            oracle = card_info.get('oracle_text', '') or card_info.get('flavor_text', '') or ''
            # Truncate oracle text to ~200 chars
            if len(oracle) > 200:
                oracle_short = oracle[:197].rstrip() + '...'
            else:
                oracle_short = oracle

            enriched_lines.append(f"{qty} {name} (mana_cost: {mana_cost}) - Oracle: {oracle_short}")

        enriched_content = '\n'.join(enriched_lines)

        # Combine information
        header = "📋 **CURRENT DECK**"
        if missing_cards:
            header += f"\n\n⚠️ Cards not found in Scryfall (will show N/A): {len(missing_cards)}"
        result = f"{header}\n{enriched_content}\n\n{curve_text}"
        return result
        
    except Exception as e:
        return f"Error getting deck information: {str(e)}"

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    # Find .env file in project root
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    load_dotenv(env_file)
    print(f"📁 Loading environment variables from: {env_file}")
except ImportError:
    print("⚠️  python-dotenv is not installed")
except Exception as e:
    print(f"⚠️  Error loading .env: {e}")  
  
# Configure API key  
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    print("⚠️  WARNING: OPENAI_API_KEY not found in environment variables")
    print("   Please configure your API key with: export OPENAI_API_KEY='your-api-key'")
else:
    os.environ["OPENAI_API_KEY"] = openai_api_key  
  
# System prompt for Magic: The Gathering agent
SYSTEM_PROMPT = """Eres un asistente especializado en Magic: The Gathering. Tienes acceso a un deck de Commander en formato MTGO que puedes consultar y modificar, además de información detallada de cartas a través de Scryfall.

Tienes las siguientes herramientas disponibles:
- view_deck: Para ver el contenido completo del deck actual
- get_deck_stats: Para obtener estadísticas del deck (total de cartas, comandante, etc.)
- modify_deck_card: Para agregar o quitar cartas del deck
- get_card_info: Para obtener información detallada de una carta específica desde Scryfall
- refresh_card_cache: Para actualizar la información en caché de una carta

El deck está en formato MTGO donde cada línea tiene el formato "cantidad nombre_carta" y la última línea es el comandante.

AUTOMÁTICAMENTE recibes en cada prompt:
- El listado completo del deck actual
- La curva de maná calculada con información de Scryfall
- Estadísticas de tierras vs hechizos
- CMC promedio del deck

Puedes ayudar con:
- Análisis del deck actual y su curva de maná
- Sugerencias de cartas para agregar o quitar basadas en la curva
- Modificaciones al deck
- Estadísticas y composición del deck
- Estrategias de juego basadas en el deck y su curva
- Información detallada de cartas específicas
- Optimización de la curva de maná

Responde de manera clara y concisa, siempre en español. Usa la información de la curva de maná para dar consejos más precisos sobre el deck.

Importante: cuando muestres el valor de maná (CMC) o la curva de maná, representa cada valor numérico usando emojis de número para mayor claridad. Por ejemplo:
- CMC 0 -> 0️⃣
- CMC 1 -> 1️⃣
- CMC 2 -> 2️⃣
- CMC 3 -> 3️⃣
- CMC 4 -> 4️⃣
- CMC 5 -> 5️⃣

Usa estos emojis siempre que menciones costos de maná o distribuciones por CMC. Incluye un pequeño resumen con emojis en la parte superior de la sección de curva de maná para que sea fácil de leer."""  
  



def _initialize_agent_resources():
    """Initialize LLM and langgraph resources when running CLI mode."""
    from langgraph.store.memory import InMemoryStore
    from langgraph.checkpoint.memory import MemorySaver
    from langchain_core.messages import HumanMessage, SystemMessage

    store = InMemoryStore()
    memory = MemorySaver()
    conversation_id = str(uuid.uuid4())
    return {
        'store': store,
        'memory': memory,
        'HumanMessage': HumanMessage,
        'SystemMessage': SystemMessage,
        'conversation_id': conversation_id,
    }
  
print("React Agent with Store - Type 'exit' to quit\n")  

def main():
    # Initialize heavy resources for CLI agent
    resources = _initialize_agent_resources()
    store = resources['store']
    memory = resources['memory']
    HumanMessage = resources['HumanMessage']
    SystemMessage = resources['SystemMessage']
    conversation_id = resources['conversation_id']

    while True:
        try:
            user_input = input("You: ")
              
            if user_input.lower() in ['salir', 'exit', 'quit']:  
                print("Goodbye!")  
                break  
              
            # Get current deck state with mana curve
            deck_info = get_enhanced_deck_info()
            
            # Build system message that includes the deck state (so the agent receives it as system prompt)
            system_msg = SystemMessage(content=SYSTEM_PROMPT + "\n\n--- CURRENT DECK STATE ---\n" + deck_info)

            # Configuration with thread_id to maintain history
            config = {
                "configurable": {"thread_id": conversation_id}
            }


            llm = init_chat_model(
                model_provider="openai",
                model="gpt-5-mini",
                base_url=os.getenv("PROXY_URL", None)
            )
            agent = create_agent(
                model=llm,
                tools=[modify_deck_card, view_deck, get_deck_stats, get_card_info, refresh_card_cache],
                system_prompt=system_msg.content,
                checkpointer=memory,
                store=store,
            )

            # Invoke agent with system message first, then the user message
            response = agent.invoke(
                {"messages": [system_msg, HumanMessage(content=user_input)]},
                config=config,
            )
              
            # Get response  
            assistant_message = response["messages"][-1]  
            assistant_response = assistant_message.content  
              
            print(f"Assistant: {assistant_response}\n")
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            print("Try again or type 'exit' to quit\n")

if __name__ == "__main__":
    main()

