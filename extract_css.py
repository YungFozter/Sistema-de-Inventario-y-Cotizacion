import os

html_path = r'f:\Proyectos\ProyectoCotizacion\ProyectoCotizacion\templates\admin\admin_dashboard.html'
css_path = r'f:\Proyectos\ProyectoCotizacion\ProyectoCotizacion\static\css\admin_dashboard.css'

with open(html_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if '<style>' in line and start_idx == -1:
        start_idx = i
    if '</style>' in line:
        end_idx = i

if start_idx != -1 and end_idx != -1:
    css_content = ''.join(lines[start_idx+1:end_idx])
    
    os.makedirs(os.path.dirname(css_path), exist_ok=True)
    with open(css_path, 'w', encoding='utf-8') as f:
        f.write(css_content)
        
    # Usually we put the link tag where the style tag was, or in a block.
    # We will just replace it where it was found.
    new_html = lines[:start_idx] + ['<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/admin_dashboard.css\') }}">\n'] + lines[end_idx+1:]
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.writelines(new_html)
    
    print('Successfully separated CSS for admin_dashboard.html!')
else:
    print('Style tag not found.')
