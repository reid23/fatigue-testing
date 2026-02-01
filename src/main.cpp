#include <Arduino.h>
#include <TMCStepper.h>
#include <EEPROM.h>
#include <HX711.h>
#include <Wire.h>

#define CS_PIN_MOTOR 10
#define RSENSE 0.022F
#define DIAG_PIN 4
#define EN_PIN 3

#define ENCODER_SCL_PIN 16
#define ENCODER_SDA_PIN 17

#define LOAD_CELL_DT_PIN 18
#define LOAD_CELL_SCK_PIN 19

#define USTEPS 64

// #define DEBUG
#define ACC_UNIT_CONVERSION 0.015270994830222222
#define VEL_UNIT_CONVERSION 1.3981013333333334

#define USTEPS_PER_MM 40*USTEPS
// #define MMPS_TO_5160VEL 7158.278826666667
#define MMPS_TO_5160VEL USTEPS_PER_MM*VEL_UNIT_CONVERSION
// #define MMPSPS_TO_5160ACC 78.18749353073778
#define MMPSPS_TO_5160ACC USTEPS_PER_MM*ACC_UNIT_CONVERSION

#define MAX_ACC 500.0
#define FAST_STOP_ACC 50000.0

#define CLEAR_OF_SAMPLE 5.0 // distance to go clear of the sample
#define X_MAX 65

#define V_START 5
#define V_STOP 5

TMC5160Stepper motor = TMC5160Stepper(CS_PIN_MOTOR, RSENSE);
SPISettings settings = SPISettings(3000000, MSBFIRST, SPI_MODE3);

unsigned long cycle_start_stamp;
float prev_pos;
float stop_force = 10;
float zero_force_thresh = 0.5;
float fwd_vel = 50.0;
float rev_vel = 100.0;

enum State {
  FWD,
  REV,
  REV_CLEAR,
  IDLE
};
static const char hex_lookup[16] = {'0','1','2','3','4','5','6','7','8','9','A','B','C','D','E','F'};

union Data {
  struct {
    uint32_t cycle;
    uint32_t stamp;
    float force;
    float pos;
    State state;
  } nice;
  char buf[sizeof(Data::nice)];
};
uint32_t cycle_start_time;

Data data;
char hex_data[sizeof(Data::buf)*2 + 1];

void write_data_to_hex(){
  for(uint8_t i=0; i<sizeof(Data::buf); i++){
    hex_data[2*i] = hex_lookup[data.buf[i] >> 4];
    hex_data[2*i+1] = hex_lookup[data.buf[i] & 0xF];
  }
}

HX711 load_cell;

void tmc_init() {
    motor.begin();

    CHOPCONF_t chopconf{0};
    chopconf.tbl = 0b01;
    chopconf.toff = 5;
    chopconf.intpol = true;
    chopconf.hend = 1 + 3;
    chopconf.hstrt = 1 - 1;
    // TERN_(SQUARE_WAVE_STEPPING, chopconf.dedge = true);
    motor.CHOPCONF(chopconf.sr);

    motor.rms_current(1800, 0.25);
    motor.microsteps(USTEPS);
    motor.iholddelay(10);
    motor.TPOWERDOWN(128); // ~2s until driver lowers to hold current
    motor.diag0_stall(true);
    motor.en_pwm_mode(0);
    // motor.stored.stealthChop_enabled = 0; // idk what this is its from dipc

    TMC2160_n::PWMCONF_t pwmconf{0};
    pwmconf.pwm_lim = 12;
    pwmconf.pwm_reg = 8;
    pwmconf.pwm_autograd = true;
    pwmconf.pwm_autoscale = true;
    pwmconf.pwm_freq = 0b01;
    pwmconf.pwm_grad = 14;
    pwmconf.pwm_ofs = 36;
    
    motor.PWMCONF(pwmconf.sr);
    // TERN(HYBRID_THRESHOLD, motor.set_pwm_thrs(hyb_thrs), UNUSED(hyb_thrs));
    motor.GSTAT(); // Clear GSTAT
    motor.VMAX(uint32_t(fwd_vel*MMPS_TO_5160VEL));
    motor.AMAX(uint16_t(MAX_ACC*MMPSPS_TO_5160ACC));
    motor.DMAX(uint16_t(MAX_ACC*MMPSPS_TO_5160ACC));
    motor.v1(0);
    motor.d1(1000);
    motor.a1(1000);
    motor.XACTUAL(0);
    motor.VSTART(uint32_t(V_START*MMPS_TO_5160VEL));
    motor.VSTOP(uint32_t(V_START*MMPS_TO_5160VEL));

    motor.RAMPMODE(0);
    motor.XTARGET(0);
}

void encoder_init() {
  pinMode(ENCODER_SCL_PIN, OUTPUT);
  pinMode(ENCODER_SDA_PIN, OUTPUT);
  Wire1.setClock(1000000);
  Wire1.begin();
}

int32_t rots = 0;
int16_t raw_angle = 0;
int16_t prev_angle = 0;
void read_encoder(){
  prev_angle = raw_angle;
  Wire1.beginTransmission(0x36);
  Wire1.write(0x0E);
  Wire1.endTransmission();
  Wire1.requestFrom(0x36, 2);
  raw_angle = Wire1.read() << 8;
  raw_angle += Wire1.read();
  if(raw_angle - prev_angle > 2048){
    rots--;
  } else if (raw_angle - prev_angle < -2048) {
    rots++;
  }
}

float get_encoder_pos(){
  return -5.0*((float)rots + (float)raw_angle/4098.0);
}

void setup() {
  Serial.begin(2500000);
  pinMode(DIAG_PIN, INPUT);
  pinMode(EN_PIN, OUTPUT);
  pinMode(CS_PIN_MOTOR, OUTPUT);
  digitalWrite(EN_PIN, LOW);
  // digitalWrite(CS_PIN_MOTOR, HIGH);

  load_cell.begin(LOAD_CELL_DT_PIN, LOAD_CELL_SCK_PIN);
  load_cell.set_scale(20149.5923684438);
  load_cell.tare(100);

  SPI.begin();

  #ifdef DEBUG
  Serial.println(motor.test_connection());
  Serial.println(motor.DRV_STATUS(), BIN);
  #endif
  digitalWrite(EN_PIN, LOW);
  tmc_init();
  encoder_init();
  hex_data[sizeof(hex_data)-1] = '\n';
  data.nice.state = State::IDLE;
}

String cmd;
char c;
void deal_with_serial() {
  while (Serial.available()){
    c = Serial.read();
    cmd.append(c);
    if(c=='\n'){
      break;
    }
  }
  if(!cmd.endsWith('\n')){
    return; //not ready to process yet
  }
  if(cmd.startsWith("SET")){
    // set parameters
    // SET [STOP FORCE] [CLEAR FORCE] [FEED RATE] [RETRACT RATE]
    cmd = cmd.substring(cmd.indexOf(' ')+1);
    stop_force = cmd.substring(0, cmd.indexOf(' ')+1).toFloat();
    cmd = cmd.substring(cmd.indexOf(' ')+1);
    zero_force_thresh = cmd.substring(0, cmd.indexOf(' ')+1).toFloat();
    cmd = cmd.substring(cmd.indexOf(' ')+1);
    fwd_vel = cmd.substring(0, cmd.indexOf(' ')+1).toFloat();
    cmd = cmd.substring(cmd.indexOf(' ')+1);
    rev_vel = cmd.toFloat();
  } else if (cmd.startsWith("BEGIN")) {
    //* start the test
    motor.DMAX(uint16_t(FAST_STOP_ACC*MMPSPS_TO_5160ACC));
    motor.XTARGET(X_MAX*USTEPS_PER_MM);
    data.nice.state = State::FWD;
    data.nice.cycle += 1;
    cycle_start_stamp = micros();
    motor.VMAX(uint32_t(fwd_vel*MMPS_TO_5160VEL));
  } else if (cmd.startsWith("G0")) {
    //* G for GO(TO), utility to go to position
    motor.XTARGET(int32_t(cmd.substring(2).toFloat()*USTEPS_PER_MM));
  }
  cmd = "";

}

void loop() {
  data.nice.force = load_cell.get_units(1);
  read_encoder();
  data.nice.pos = get_encoder_pos();
  // int32_t xactual = motor.XACTUAL();
  // if(xactual!=0){
    // prev_pos = data.nice.pos;
    // data.nice.pos = ((float)xactual)/((float)USTEPS_PER_MM);
  // }
  data.nice.stamp = micros() - cycle_start_stamp;

  if(data.nice.state==State::FWD){
      if(data.nice.force>=stop_force){
        motor.XTARGET(0);
        data.nice.state = State::REV;
        motor.VMAX(uint32_t(rev_vel*MMPS_TO_5160VEL));
      } else if(motor.position_reached()){
        //* avoid stalled state in edge case
        // if we never hit the force threshold 
        // it means we probably broke the rig
        // but we'll just keep continuing
        motor.XTARGET(0);
        data.nice.state = State::REV;
        motor.VMAX(uint32_t(rev_vel*MMPS_TO_5160VEL));
      }
  } else if(data.nice.state==State::REV){
      #ifdef DEBUG
      Serial.println(data.nice.force < zero_force_thresh);
      #endif
      if(data.nice.force < zero_force_thresh){
        motor.DMAX(uint16_t(MAX_ACC*MMPSPS_TO_5160ACC));
        motor.XTARGET(max(data.nice.pos-CLEAR_OF_SAMPLE, 0.0)*USTEPS_PER_MM);
        data.nice.state = State::REV_CLEAR;
      } else if(motor.position_reached()) {
        //* avoid stalled state in edge case
        // if we never get sufficiently 
        // low force despite retracting 
        // all the way, somethings probably
        // broken. cope!! we'll just keep going
        data.nice.state = State::REV_CLEAR;
        #ifdef DEBUG
        Serial.println("HERE!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!");
        #endif
      }
  } else if(data.nice.state==State::REV_CLEAR) {
      if(motor.position_reached()){
        motor.DMAX(uint16_t(FAST_STOP_ACC*MMPSPS_TO_5160ACC));
        motor.XTARGET(X_MAX*USTEPS_PER_MM);
        data.nice.state = State::FWD;
        data.nice.cycle += 1;
        cycle_start_stamp = micros();
        motor.VMAX(uint32_t(fwd_vel*MMPS_TO_5160VEL));
      }
  } else if(data.nice.state==State::IDLE){
      deal_with_serial();
  }

  write_data_to_hex();
  
  #ifdef DEBUG
  Serial.print("N=");
  Serial.print(data.nice.cycle);
  Serial.print(", \tF=");
  Serial.print(data.nice.force);
  Serial.print(", \tx=");
  Serial.print(data.nice.pos);
  Serial.print(", \tstate=");
  Serial.print(data.nice.state);
  Serial.print(", \t");
  Serial.print(stop_force);
  Serial.print(", \t");
  Serial.print(zero_force_thresh);
  Serial.print(", \t");
  Serial.print(fwd_vel);
  Serial.print(", \t");
  Serial.print(rev_vel);
  Serial.println();
  #else
  Serial.write(hex_data, sizeof(hex_data));
  #endif

}