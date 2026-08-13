def find_unmatched(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    stack = []
    
    for i, line in enumerate(lines, 1):
        for char in line:
            if char == '{':
                stack.append(i)
            elif char == '}':
                if stack:
                    stack.pop()
                else:
                    print(f"Unmatched '}}' found at line {i}")
                    
    if stack:
        print(f"Unmatched '{{' found at lines: {stack}")
    else:
        print("All braces are matched.")

find_unmatched(r"f:\Proyectos\ProyectoCotizacion\ProyectoCotizacion\templates\productos\productos.html")
