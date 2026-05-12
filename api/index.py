# api/index.py
# Aplicación principal Flask con Firebase Realtime Database
# Despliegue listo para Vercel

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import firebase_admin
from firebase_admin import credentials, db
import os
import json
from datetime import datetime

# Importar autenticación
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth_manager.security import login_required, check_credentials

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.urandom(24)

# ---------- INICIALIZAR FIREBASE REALTIME DATABASE ----------
firebase_initialized = False
rtdb_ref = None

# Tu URL de Realtime Database (de la captura)
DATABASE_URL = "https://brawl-67616-default-rtdb.firebaseio.com/"

try:
    # Opción 1: Usar variable de entorno en Vercel
    if os.getenv('FIREBASE_CREDENTIALS'):
        cred_dict = json.loads(os.getenv('FIREBASE_CREDENTIALS'))
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred, {
            'databaseURL': DATABASE_URL
        })
        firebase_initialized = True
        print("✅ Firebase Realtime Database inicializado con variable de entorno")
    
    # Opción 2: Usar archivo local (solo para pruebas)
    elif os.path.exists('serviceAccountKey.json'):
        cred = credentials.Certificate('serviceAccountKey.json')
        firebase_admin.initialize_app(cred, {
            'databaseURL': DATABASE_URL
        })
        firebase_initialized = True
        print("✅ Firebase Realtime Database inicializado con archivo local")
    
    else:
        print("⚠️ No se encontraron credenciales de Firebase. Modo demo sin datos reales.")
    
    if firebase_initialized:
        rtdb_ref = db.reference('/productos')  # Referencia a la colección 'productos'

except Exception as e:
    print(f"❌ Error inicializando Firebase: {e}")

# ---------- FUNCIONES AUXILIARES ----------

def get_available_products():
    """Obtiene solo los productos con status 'disponible' para el catálogo público"""
    if not firebase_initialized or not rtdb_ref:
        return []
    try:
        all_products = rtdb_ref.get()
        if not all_products:
            return []
        
        available = []
        for pid, product in all_products.items():
            if product.get('status') == 'disponible':
                product['id'] = pid
                # Convertir string de imágenes a lista
                if 'imagenes' in product and isinstance(product['imagenes'], str):
                    product['imagenes_list'] = [img.strip() for img in product['imagenes'].split(',') if img.strip()]
                else:
                    product['imagenes_list'] = []
                available.append(product)
        return available
    except Exception as e:
        print(f"Error obteniendo productos disponibles: {e}")
        return []

def get_all_products():
    """Obtiene TODOS los productos para el panel admin"""
    if not firebase_initialized or not rtdb_ref:
        return []
    try:
        all_products = rtdb_ref.get()
        if not all_products:
            return []
        
        products = []
        for pid, product in all_products.items():
            product['id'] = pid
            if 'imagenes' in product and isinstance(product['imagenes'], str):
                product['imagenes_list'] = [img.strip() for img in product['imagenes'].split(',') if img.strip()]
            else:
                product['imagenes_list'] = []
            products.append(product)
        return products
    except Exception as e:
        print(f"Error obteniendo todos los productos: {e}")
        return []

# ---------- RUTAS PÚBLICAS ----------

@app.route('/')
def index():
    """Página principal del catálogo para clientes"""
    products = get_available_products()
    return render_template('index.html', products=products)

# ---------- RUTAS DEL PANEL ADMINISTRATIVO ----------

@app.route('/admin')
def admin_panel():
    """Panel de gestión exclusivo para Elena"""
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))
    products = get_all_products()
    return render_template('admin.html', products=products)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Formulario de inicio de sesión"""
    if request.method == 'POST':
        user = request.form.get('username')
        pwd = request.form.get('password')
        if check_credentials(user, pwd):
            session['logged_in'] = True
            return redirect(url_for('admin_panel'))
        else:
            return render_template('admin.html', error="Credenciales incorrectas", login_form=True)
    return render_template('admin.html', login_form=True)

@app.route('/admin/logout')
def admin_logout():
    """Cerrar sesión"""
    session.pop('logged_in', None)
    return redirect(url_for('index'))

# ---------- API CRUD PARA PRODUCTOS (Realtime Database) ----------

@app.route('/api/productos', methods=['POST'])
@login_required
def crear_producto():
    """Crear un nuevo producto"""
    if not firebase_initialized or not rtdb_ref:
        return jsonify({"error": "Firebase no disponible"}), 500
    
    data = request.get_json()
    titulo = data.get('titulo')
    precio = data.get('precio')
    descripcion = data.get('descripcion', '')
    imagenes = data.get('imagenes', '')
    status = data.get('status', 'disponible')
    
    if not titulo or not precio:
        return jsonify({"error": "Título y precio son obligatorios"}), 400
    
    nuevo_producto = {
        'titulo': titulo,
        'precio': float(precio),
        'descripcion': descripcion,
        'imagenes': imagenes,
        'status': status,
        'created_at': datetime.now().isoformat()
    }
    
    # Realtime Database genera un ID automático con push()
    new_ref = rtdb_ref.push(nuevo_producto)
    return jsonify({"id": new_ref.key, "message": "Producto creado"}), 201

@app.route('/api/productos/<product_id>', methods=['PUT'])
@login_required
def actualizar_producto(product_id):
    """Actualizar un producto existente"""
    if not firebase_initialized or not rtdb_ref:
        return jsonify({"error": "Firebase no disponible"}), 500
    
    data = request.get_json()
    updates = {}
    
    if 'titulo' in data:
        updates['titulo'] = data['titulo']
    if 'precio' in data:
        updates['precio'] = float(data['precio'])
    if 'descripcion' in data:
        updates['descripcion'] = data['descripcion']
    if 'imagenes' in data:
        updates['imagenes'] = data['imagenes']
    if 'status' in data:
        updates['status'] = data['status']
    
    if not updates:
        return jsonify({"error": "No hay datos para actualizar"}), 400
    
    producto_ref = db.reference(f'/productos/{product_id}')
    producto_ref.update(updates)
    return jsonify({"message": "Producto actualizado"})

@app.route('/api/productos/<product_id>', methods=['DELETE'])
@login_required
def eliminar_producto(product_id):
    """Eliminar un producto"""
    if not firebase_initialized or not rtdb_ref:
        return jsonify({"error": "Firebase no disponible"}), 500
    
    producto_ref = db.reference(f'/productos/{product_id}')
    producto_ref.delete()
    return jsonify({"message": "Producto eliminado"})

@app.route('/admin/exportar')
@login_required
def exportar_inventario():
    """Exportar todos los productos como JSON"""
    products = get_all_products()
    return jsonify(products)

# ---------- EJECUCIÓN LOCAL (para pruebas) ----------
if __name__ == '__main__':
    app.run(debug=True)