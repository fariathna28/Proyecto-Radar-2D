"""
Radar 2D - Proyecto 2
CE-1104 Fundamentos de Sistemas Computacionales
Tecnologico de Costa Rica - I Semestre 2026

Si SIMULATION_MODE = True, el radar funciona sin Arduino (modo prueba)
Si SIMULATION_MODE = False, se conecta al Arduino por el puerto serial

Comentado con ayuda de Claude
"""

import tkinter as tk
import math
import time
import threading
import queue



# --- Aqui se decide si usar el simulador o el Arduino real ---
SIMULATION_MODE = False    # cambiar a False cuando el Arduino este listo

# --- Configuracion del radar ---
RADAR_MAX_CM    = 200.0   # hasta donde mide el sensor (en cm)
RADAR_MIN_CM    = 2.0     # lecturas menores a esto se ignoran (muy cerca)
TRACK_THRESH    = 10.0    # si dos lecturas estan a menos de esto, son el mismo objeto
OBJ_TIMEOUT     = 3.0     # si un objeto no se detecta en X segundos, se borra
PREDICT_T       = 1.5     # cuantos segundos hacia el futuro predecimos
GUI_REFRESH_MS  = 50      # cada cuantos ms se actualiza la pantalla
CANVAS_SIZE     = 510     # tamanio del cuadro del radar

# --- Puerto serial (solo importa si SIMULATION_MODE = False) ---
SERIAL_PORT = 'COM5'      # cambiar al puerto correcto (COM3, COM4, etc.)
SERIAL_BAUD = 9600        # tiene que coincidir con el Serial.begin() del Arduino

# --- Colores de la interfaz ---
C = {
    'bg':         '#050e05',
    'panel':      '#060f06',
    'radar':      '#020a02',
    'grid':       '#004a15',
    'sweep':      '#00ff41',
    'text_main':  '#00ff41',
    'text_dim':   '#008820',
    'obj':        '#ffff00',
    'pred':       '#ff6600',
    'alert_on':   '#ff3333',
    'alert_off':  '#280000',
}


# =============================================================================
# PARTE 1: como rastreamos los objetos detectados
# =============================================================================

class ObjetoDetectado:
    """
    Cada vez que el sensor encuentra algo, se guarda aqui.
    Llevamos registro de donde estuvo, a que velocidad va
    y hacia donde va a ir (prediccion).
    """
    MAX_TRAIL = 14  # cuantas posiciones pasadas guardamos

    def __init__(self, obj_id, x, y, ts):
        self.id      = obj_id
        self.x       = x
        self.y       = y
        self.last_ts = ts
        self.vx      = 0.0   # velocidad en x
        self.vy      = 0.0   # velocidad en y
        self.speed   = 0.0   # rapidez total
        self.trail   = [(x, y)]  # historial de posiciones

    def actualizar(self, x, y, ts):
        """El objeto se movio, actualizamos su posicion y velocidad."""
        dt = ts - self.last_ts

        # evitar division entre cero
        if dt <= 0.0:
            dt = 0.001

        self.vx    = (x - self.x) / dt
        self.vy    = (y - self.y) / dt
        self.speed = math.hypot(self.vx, self.vy)
        self.x, self.y, self.last_ts = x, y, ts

        self.trail.append((x, y))

        # si el historial esta muy largo, borramos el mas viejo
        if len(self.trail) >= self.MAX_TRAIL + 1:
            self.trail.pop(0)

    def predecir(self, t):
        """
        Usamos las formulas del movimiento parabolico para estimar
        donde va a estar el objeto en 't' segundos:
            x(t) = x0 + vx * t
            y(t) = y0 + vy * t - 0.5 * g * t^2
        """
        g = 9.8
        return (
            self.x + self.vx * t,
            self.y + self.vy * t - 0.5 * g * t * t
        )


class Tracker:
    """
    Se encarga de llevar la lista de objetos detectados.
    Cuando llega una nueva lectura, decide si es un objeto nuevo
    o si ya lo estabamos rastreando.
    """
    def __init__(self):
        self.objetos  = []
        self._next_id = 1

    def procesar(self, angulo, distancia, ts):
        """Recibe una lectura del sensor y la asocia a un objeto."""

        # ignorar lecturas fuera del rango util del sensor
        if distancia <= RADAR_MIN_CM:
            return
        if distancia >= RADAR_MAX_CM:
            return

        # convertir de coordenadas polares (angulo, distancia) a cartesianas (x, y)
        rad = math.radians(angulo)
        x   = distancia * math.cos(rad)
        y   = distancia * math.sin(rad)

        # revisar si ya hay un objeto cerca de esa posicion
        for obj in self.objetos:
            if math.hypot(obj.x - x, obj.y - y) <= TRACK_THRESH:
                obj.actualizar(x, y, ts)
                return

        # si no habia ninguno, es un objeto nuevo
        self.objetos.append(ObjetoDetectado(self._next_id, x, y, ts))
        self._next_id += 1

    def borrar_viejos(self, ahora):
        """Borra los objetos que ya no aparecen hace rato."""
        vivos = []
        for obj in self.objetos:
            if (ahora - obj.last_ts) <= OBJ_TIMEOUT:
                vivos.append(obj)
        self.objetos = vivos


# =============================================================================
# PARTE 2: la interfaz grafica
# =============================================================================

class RadarApp:
    def __init__(self, root):
        self.root          = root
        self.tracker       = Tracker()
        self.angulo_actual = 0.0
        self.conectado     = False
        self._alerta_on    = False
        self._frame_espera = 0
        self._tiempo_inicio = time.time()
        self._cola = queue.Queue()  # aqui llegan los datos del hilo del sensor

        # titulo de la ventana segun el modo
        if SIMULATION_MODE:
            titulo = "Radar 2D - Modo Simulacion"
        else:
            titulo = f"Radar 2D - Puerto {SERIAL_PORT}"

        self.root.title(titulo)
        self.root.geometry("1060x685")
        self.root.configure(bg=C['bg'])
        self.root.resizable(False, False)

        self._construir_ventana()
        self._dibujar_fondo_radar()
        self._mostrar_pantalla_espera()

        # arrancar los loops de actualizacion
        self._loop_principal()
        self._loop_alerta()
        self._loop_animacion_espera()

    def _construir_ventana(self):
        """Arma todos los elementos visuales de la ventana."""

        # barra superior con titulo
        encabezado = tk.Frame(self.root, bg=C['bg'], height=50)
        encabezado.pack(fill=tk.X)
        encabezado.pack_propagate(False)

        tk.Label(encabezado, text="Proyecto: Radar 2D",
                 bg=C['bg'], fg=C['text_main'],
                 font=("Arial", 16, "bold")).pack(side=tk.LEFT, padx=18)

        if SIMULATION_MODE:
            info = "Simulacion Activa"
        else:
            info = f"Puerto: {SERIAL_PORT}"

        tk.Label(encabezado, text=info,
                 bg=C['bg'], fg=C['text_dim'],
                 font=("Arial", 10)).pack(side=tk.RIGHT, padx=18)

        # area principal
        cuerpo = tk.Frame(self.root, bg=C['bg'])
        cuerpo.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)

        # columna izquierda: canvas del radar
        col_izq = tk.Frame(cuerpo, bg=C['bg'])
        col_izq.pack(side=tk.LEFT)

        self.canvas = tk.Canvas(col_izq,
                                width=CANVAS_SIZE, height=CANVAS_SIZE,
                                bg=C['radar'], highlightthickness=1,
                                highlightbackground=C['grid'])
        self.canvas.pack()

        # barra de estado debajo del radar
        barra = tk.Frame(col_izq, bg=C['panel'], height=28)
        barra.pack(fill=tk.X, pady=(10, 0))
        barra.pack_propagate(False)

        self.lbl_estado = tk.Label(barra, text="Desconectado",
                                   bg=C['panel'], fg='#ff4444',
                                   font=("Arial", 10, "bold"))
        self.lbl_estado.pack(side=tk.LEFT, padx=10)

        self.lbl_angulo = tk.Label(barra, text="Angulo: ---",
                                   bg=C['panel'], fg=C['text_main'],
                                   font=("Arial", 10))
        self.lbl_angulo.pack(side=tk.LEFT, padx=12)

        self.lbl_objetos = tk.Label(barra, text="Objetos: 0",
                                    bg=C['panel'], fg=C['text_main'],
                                    font=("Arial", 10))
        self.lbl_objetos.pack(side=tk.LEFT, padx=12)

        self.lbl_tiempo = tk.Label(barra, text="Tiempo: 00:00",
                                   bg=C['panel'], fg=C['text_dim'],
                                   font=("Arial", 10))
        self.lbl_tiempo.pack(side=tk.RIGHT, padx=12)

        # columna derecha: panel de informacion
        col_der = tk.Frame(cuerpo, bg=C['panel'],
                           highlightthickness=1,
                           highlightbackground=C['grid'])
        col_der.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(12, 0))

        # fila superior del panel: indicador de alerta
        fila_top = tk.Frame(col_der, bg=C['panel'])
        fila_top.pack(fill=tk.X, padx=12, pady=(10, 0))

        tk.Label(fila_top, text="Alerta:",
                 bg=C['panel'], fg=C['text_dim'],
                 font=("Arial", 10)).pack(side=tk.LEFT)

        self._cv_led = tk.Canvas(fila_top, width=16, height=16,
                                 bg=C['panel'], highlightthickness=0)
        self._cv_led.pack(side=tk.LEFT, padx=(4, 0))
        self._led_dot = self._cv_led.create_oval(2, 2, 14, 14,
                                                  fill=C['alert_off'],
                                                  outline='')

        # caja de texto con info de los objetos
        self.txt = tk.Text(col_der, bg=C['panel'], fg=C['text_main'],
                           font=("Courier", 10), state=tk.DISABLED,
                           relief=tk.FLAT, padx=10, pady=6)
        self.txt.pack(fill=tk.BOTH, expand=True, padx=6, pady=(8, 8))

    def _dibujar_fondo_radar(self):
        """Dibuja los circulos, la cuadricula y las marcas de angulo del radar."""
        c = CANVAS_SIZE / 2   # centro del canvas
        r = CANVAS_SIZE / 2 - 24  # radio maximo

        # 4 circulos concentricos
        for i in range(1, 5):
            frac = i / 4.0
            rr   = r * frac
            self.canvas.create_oval(c - rr, c - rr, c + rr, c + rr,
                                    outline=C['grid'], width=1, tags="bg")

        # cruz central (lineas de referencia)
        self.canvas.create_line(c, c - r, c, c + r,
                                fill=C['grid'], width=1, tags="bg")
        self.canvas.create_line(c - r, c, c + r, c,
                                fill=C['grid'], width=1, tags="bg")

        # marcas de angulo de 0 a 180 grados
        for deg in range(0, 181, 30):
            rad_d = math.radians(deg)
            x_in  = c + (r - 8) * math.cos(rad_d)
            y_in  = c - (r - 8) * math.sin(rad_d)
            x_out = c + r * math.cos(rad_d)
            y_out = c - r * math.sin(rad_d)
            self.canvas.create_line(x_in, y_in, x_out, y_out,
                                    fill=C['text_dim'], width=1, tags="bg")

            # numero del angulo
            xl = c + (r + 15) * math.cos(rad_d)
            yl = c - (r + 15) * math.sin(rad_d)
            self.canvas.create_text(xl, yl, text=f"{deg}°",
                                    fill=C['text_dim'],
                                    font=("Arial", 8), tags="bg")

        # punto en el centro
        self.canvas.create_oval(c - 4, c - 4, c + 4, c + 4,
                                fill=C['text_main'], outline='', tags="bg")

    def _dibujar_dinamico(self):
        """Redibuja la linea de barrido y los objetos detectados."""
        self.canvas.delete("dyn")

        # si aun no hay conexion, no dibujamos nada
        if not self.conectado:
            return

        c    = CANVAS_SIZE / 2
        maxr = CANVAS_SIZE / 2 - 24
        ang  = self.angulo_actual

        # linea de barrido
        rad_a = math.radians(ang)
        ex    = c + maxr * math.cos(rad_a)
        ey    = c - maxr * math.sin(rad_a)
        self.canvas.create_line(c, c, ex, ey,
                                fill=C['sweep'], width=2, tags="dyn")

        # dibujar cada objeto detectado
        escala = maxr / RADAR_MAX_CM
        for obj in self.tracker.objetos:
            ox = c + obj.x * escala
            oy = c - obj.y * escala

            # ignorar si esta fuera del circulo
            if math.hypot(ox - c, oy - c) >= maxr + 6.0:
                continue

            # punto del objeto
            self.canvas.create_oval(ox - 5, oy - 5, ox + 5, oy + 5,
                                    fill=C['obj'], outline='', tags="dyn")

            # etiqueta con el ID
            self.canvas.create_text(ox + 10, oy - 10,
                                    text=f"ID:{obj.id}",
                                    fill=C['obj'],
                                    font=("Arial", 8, "bold"),
                                    anchor="w", tags="dyn")

            # linea de prediccion hacia donde va a ir
            px, py = obj.predecir(PREDICT_T)
            prx    = c + px * escala
            pry    = c - py * escala
            self.canvas.create_line(ox, oy, prx, pry,
                                    fill=C['pred'],
                                    dash=(4, 4), width=2, tags="dyn")

    def _actualizar_panel(self):
        """Actualiza el texto del panel lateral con la info de los objetos."""
        self.txt.config(state=tk.NORMAL)
        self.txt.delete("1.0", tk.END)

        if not self.conectado:
            self.txt.insert(tk.END, "\nEsperando datos del hardware...\n")
        elif len(self.tracker.objetos) == 0:
            self.txt.insert(tk.END, "\nBuscando objetos...\n")
        else:
            for obj in self.tracker.objetos:
                dist   = math.hypot(obj.x, obj.y)
                px, py = obj.predecir(PREDICT_T)

                info = (
                    f"--- OBJETO #{obj.id} ---\n"
                    f" Distancia : {dist:.1f} cm\n"
                    f" Posicion  : ({obj.x:.1f}, {obj.y:.1f})\n"
                    f" Velocidad : {obj.speed:.2f} cm/s\n"
                    f" Prediccion: ({px:.1f}, {py:.1f})\n\n"
                )
                self.txt.insert(tk.END, info)

        self.txt.config(state=tk.DISABLED)

    def _actualizar_barra(self):
        """Actualiza la barra inferior con el angulo, objetos y tiempo."""
        segundos = int(time.time() - self._tiempo_inicio)
        mm, ss   = divmod(segundos, 60)
        self.lbl_tiempo.config(text=f"Tiempo: {mm:02d}:{ss:02d}")

        if self.conectado:
            self.lbl_estado.config(text="Conectado", fg=C['sweep'])
            self.lbl_angulo.config(text=f"Angulo: {self.angulo_actual:.1f}")
            self.lbl_objetos.config(text=f"Objetos: {len(self.tracker.objetos)}")

    def _mostrar_pantalla_espera(self):
        """Muestra un mensaje mientras no llegan datos."""
        self.canvas.delete("wait")
        c = CANVAS_SIZE / 2
        self.canvas.create_rectangle(c - 120, c - 40, c + 120, c + 40,
                                     fill=C['panel'], outline=C['grid'],
                                     tags="wait")
        self.canvas.create_text(c, c, text="Esperando datos...",
                                fill=C['text_main'],
                                font=("Arial", 12), tags="wait")

    def _loop_principal(self):
        """Loop que se ejecuta cada 50ms para actualizar todo."""

        # procesar todos los datos que llegaron desde el hilo
        while not self._cola.empty():
            try:
                angulo, distancia, ts = self._cola.get_nowait()
                self.angulo_actual    = angulo
                self.tracker.procesar(angulo, distancia, ts)

                # primera vez que llegan datos: quitar pantalla de espera
                if not self.conectado:
                    self.conectado = True
                    self.canvas.delete("wait")
            except queue.Empty:
                break

        self.tracker.borrar_viejos(time.time())
        self._dibujar_dinamico()
        self._actualizar_panel()
        self._actualizar_barra()

        # volver a llamarse a si mismo en 50ms
        self.root.after(GUI_REFRESH_MS, self._loop_principal)

    def _loop_alerta(self):
        """Hace parpadear el LED de alerta cuando hay objetos."""
        self._alerta_on = not self._alerta_on
        hay_objetos     = self.conectado and len(self.tracker.objetos) >= 1

        color = C['alert_off']
        if hay_objetos and self._alerta_on:
            color = C['alert_on']

        self._cv_led.itemconfig(self._led_dot, fill=color)
        self.root.after(500, self._loop_alerta)

    def _loop_animacion_espera(self):
        """Anima la pantalla de espera mientras no hay datos."""
        if not self.conectado:
            self._frame_espera += 1
            self._mostrar_pantalla_espera()
        self.root.after(500, self._loop_animacion_espera)

    def recibir_dato(self, angulo, distancia):
        """El hilo del sensor llama esto para mandar datos a la GUI."""
        self._cola.put((angulo, distancia, time.time()))


# =============================================================================
# PARTE 3: fuentes de datos (simulacion y arduino)
# =============================================================================

def hilo_sensor(app):
    """Decide si usar el simulador o el Arduino real."""
    if SIMULATION_MODE:
        _simular(app)
    else:
        _leer_arduino(app)


def _simular(app):
    """Genera objetos ficticios para probar sin hardware."""
    time.sleep(1)
    angulo = 0.0
    paso   = 3.0

    while True:
        angulo += paso
        if angulo >= 180.0:
            paso = -3.0
        if angulo <= 0.0:
            paso = 3.0

        t    = time.time()
        dist = RADAR_MAX_CM + 10.0   # por defecto: nada detectado

        # objeto 1: aparece entre 75 y 105 grados
        if 75.0 <= angulo <= 105.0:
            dist = 45.0 + 8.0 * math.sin(t * 0.6)

        # objeto 2: aparece entre 20 y 50 grados
        if 20.0 <= angulo <= 50.0:
            dist = 110.0 + 15.0 * math.sin(t * 0.4)

        app.recibir_dato(angulo, dist)
        time.sleep(0.05)


def _leer_arduino(app):
    """
    Lee los datos que manda el Arduino por el puerto serial.
    El Arduino manda lineas con el formato: "angulo,distancia"
    Por ejemplo: "090,45.30"
    """
    try:
        import serial
        conn = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1)
        time.sleep(2)   # esperar que el Arduino arranque

        while True:
            if conn.in_waiting >= 1:
                linea = conn.readline().decode('utf-8', errors='ignore').strip()

                # ignorar lineas de comentario o vacias
                if not linea or linea.startswith('#'):
                    continue

                partes = linea.split(',')
                if len(partes) == 2:
                    try:
                        ang  = float(partes[0])
                        dist = float(partes[1])
                        app.recibir_dato(ang, dist)
                    except ValueError:
                        pass   # si la linea llego mal formada, la ignoramos

    except Exception as e:
        print(f"No se pudo conectar al Arduino: {e}")


# =============================================================================
# ARRANQUE
# =============================================================================

if __name__ == "__main__":
    ventana = tk.Tk()
    app     = RadarApp(ventana)

    # el sensor corre en un hilo aparte para no congelar la GUI
    hilo = threading.Thread(target=hilo_sensor, args=(app,), daemon=True)
    hilo.start()

    ventana.mainloop()
