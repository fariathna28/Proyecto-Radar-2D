#include <Servo.h> // Librería para el servo

// Pines
#define PIN_SERVO 9
#define TRIG_PIN 11
#define ECHO_PIN 12
#define LED_PIN 6

Servo servo; // Crear el servo como objeto

// Variables de movimiento
int angulo = 0;
int direccion = 1; // 1 = derecha, -1 = izquierda

// Función para medir distancia
float medirDistancia() {

    // Iniciar con el sensor apagado
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(3); //Esperar 3 segundos para iniciar

    // Enviar onda
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);

    // Esperar la respuesta de la onda
    long tiempo_respuesta = pulseIn(ECHO_PIN, HIGH, 30000);

    // Si no recibe respuesta
    if (tiempo_respuesta == 0) {
        return 0;
    }

    // Conversión a centímetros
    float distancia = tiempo_respuesta * 0.0343 / 2;

    return distancia;
}

void setup() {

    Serial.begin(9600);

    //Declarar entradas y salidas
    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);
    pinMode(LED_PIN, OUTPUT);

    servo.attach(PIN_SERVO);

    servo.write(0); //Posición inicial del servo

    Serial.println("Radar encendido");
}

void loop() {

    // Mover servo
    servo.write(angulo);

    // Dar tiempo para llegar a la posición
    delay(40);

    // Medir distancia
    float distancia = medirDistancia();

    // Encender LED si se detecta algo a 10 cm o menos
    if (distancia <= 15 && distancia > 0) {
        digitalWrite(LED_PIN, HIGH);
    }
    else {
        digitalWrite(LED_PIN, LOW);
    }

    // Enviar datos por Serial
    Serial.print(angulo);
    Serial.print(",");
    Serial.println(distancia);
    // Actualizar ángulo
    angulo += direccion;

    // Cambiar dirección al llegar a 180°
    if (angulo >= 180) {
        direccion = -1;
    }

    // Cambiar dirección al llegar a 0°
    if (angulo <= 0) {
        direccion = 1;
    }
}