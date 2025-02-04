from elevenlabs.client import ElevenLabs
import os

def text_to_speech(input_text, output_path, voice="George", api_key=None):
    try:
        # Initialize client
        client = ElevenLabs(api_key=api_key)
            
        # Generate audio from text
        audio = client.generate(
            text=input_text,
            voice=voice,
            model="eleven_multilingual_v2"
        )
        
        # Get audio bytes from generator
        audio_bytes = b"".join(audio)  # Add this line
        
        # Save audio to file
        with open(output_path, 'wb') as f:
            f.write(audio_bytes)  # Changed from audio to audio_bytes
        print(f"Audio saved successfully to {output_path}")
        
    except Exception as e:
        print(f"Error generating speech: {str(e)}")

def process_verses(verses_list, output_dir="audio", voice="George", api_key=None):
    """
    Process a list of verse pairs [reference, text, filename] and create MP3 files.
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    for verse_ref, verse_text, filename in verses_list:
        # Use the provided filename
        output_path = os.path.join(output_dir, filename)
        
        # Generate speech for this verse
        try:
            text_to_speech(verse_text, output_path, voice=voice, api_key=api_key)
            print(f"Processed {verse_ref}")
        except Exception as e:
            print(f"Error processing {verse_ref}: {str(e)}")

# Example usage
if __name__ == "__main__":
    # You can set your API key here or as an environment variable
    API_KEY = "enter_elevenlabs_api_key_here"

    verses = [
        ['LUK_2_1', 'Ahora sucedió en aquellos días que salió una orden de César Augusto de empadronar a todo el mundo.'],
        ['LUK_2_2', 'Este primer censo, se hizo cuando Cirenio era el gobernante de Siria.'],
        ['LUK_2_3', 'Y todos los hombres fueron contados, todos en su ciudad.'],
        ['LUK_2_4', 'Y subió José de Galilea, de la ciudad de Nazaret, a Judea, a Belén, la ciudad de David, porque era de la casa y familia de David,'],     
        ['LUK_2_5', 'Para ser puesto en la lista con María, su futura esposa, que estaba a punto de convertirse en madre.'],
        ['LUK_2_6', 'Y mientras estaban allí, llegó el momento de que ella diera a luz.'],
        ['LUK_2_7', 'Y ella tuvo su primer hijo; y, lo envolvió en lino, lo puso a descansar en el lugar donde el ganado tenía su comida, porque no había lugar para ellos en el mesón.'],
        ['LUK_2_8', 'Y en la misma región había pastores de ovejas en los campos, cuidando sus rebaños de noche.'],
    ]
    
    process_verses(verses, output_dir='audio/bes/luk2', api_key=API_KEY)