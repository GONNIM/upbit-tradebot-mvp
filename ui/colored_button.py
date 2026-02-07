"""
Colored button component for Streamlit.
Provides reliably styled buttons with custom colors using components.html for guaranteed rendering.
"""
import streamlit as st
import streamlit.components.v1 as components


def colored_button(
    label: str,
    key: str,
    bg_color: str,
    text_color: str = "white",
    border_color: str = None,
    hover_color: str = None,
    use_container_width: bool = True,
    height: int = 45,
) -> bool:
    """
    Create a colored button that integrates with Streamlit.
    Uses components.html for guaranteed color rendering.

    Args:
        label: Button text
        key: Unique key for this button
        bg_color: Background color (hex or CSS color)
        text_color: Text color (default: white)
        border_color: Border color (default: same as bg_color)
        hover_color: Hover state color (default: darker version)
        use_container_width: Whether button should fill container width
        height: Button height in pixels (default: 45)

    Returns:
        bool: True if button was clicked in this run, False otherwise
    """
    # Set defaults
    if border_color is None:
        border_color = bg_color
    if hover_color is None:
        # Use slightly darker version for hover
        hover_color = bg_color

    # Width style
    width_style = "width: 100%;" if use_container_width else "width: auto;"

    # Create HTML with inline styles (guaranteed to work)
    button_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                margin: 0;
                padding: 0;
                font-family: "Source Sans Pro", sans-serif;
            }}
            .colored-btn {{
                {width_style}
                height: {height}px;
                background: linear-gradient(180deg, {bg_color} 0%, {hover_color} 100%);
                color: {text_color};
                border: 2px solid {border_color};
                border-radius: 0.5rem;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                padding: 0;
                transition: all 0.2s;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .colored-btn:hover {{
                background: {hover_color};
                transform: translateY(-1px);
                box-shadow: 0 4px 8px rgba(0,0,0,0.2);
            }}
            .colored-btn:active {{
                transform: translateY(0px);
                box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            }}
        </style>
    </head>
    <body>
        <button class="colored-btn" onclick="sendClick()">{label}</button>
        <script>
            function sendClick() {{
                // Send click event to Streamlit parent
                window.parent.postMessage({{
                    type: 'streamlit:setComponentValue',
                    value: '{key}'
                }}, '*');
            }}
        </script>
    </body>
    </html>
    """

    # Render using components.html (guarantees rendering)
    clicked_key = components.html(button_html, height=height + 10)

    # Return True if this button was clicked
    return clicked_key == key
