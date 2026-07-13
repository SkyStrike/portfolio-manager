import os
from jinja2 import Environment

def render_combined_css(env: Environment, page_width: str = "1800px", chart_height: str = "40vh") -> str:
    """
    Combines static/css/style.css (base) and templates/styles.css (report overrides)
    and compiles/renders the result as a Jinja2 template.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    base_css_path = os.path.join(base_dir, "static", "css", "style.css")
    override_css_path = os.path.join(base_dir, "templates", "styles.css")
    
    with open(base_css_path, "r", encoding="utf-8") as f:
        base_css = f.read()
        
    with open(override_css_path, "r", encoding="utf-8") as f:
        override_css = f.read()
        
    # Combine base CSS and overrides
    combined_css = base_css + "\n" + override_css
    
    # Compile and render using Jinja2
    template = env.from_string(combined_css)
    return template.render(PAGE_WIDTH=page_width, CHART_HEIGHT=chart_height)
