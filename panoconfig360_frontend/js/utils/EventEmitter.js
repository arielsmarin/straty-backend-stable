/**
 * EventEmitter.js
 * Implementação simples de event emitter
 */

export class EventEmitter {
  constructor() {
    this._events = {};
  }

  on(event, listener) {
    if (!this._events[event]) {
      this._events[event] = [];
    }
    this._events[event].push(listener);
    return this;
  }

  off(event, listener) {
    if (!this._events[event]) return this;
    
    const index = this._events[event].indexOf(listener);
    if (index > -1) {
      this._events[event].splice(index, 1);
    }
    return this;
  }

  emit(event, ...args) {
    if (!this._events[event]) return false;
    
    this._events[event].forEach(listener => {
      listener.apply(this, args);
    });
    return true;
  }

  once(event, listener) {
    const onceWrapper = (...args) => {
      listener.apply(this, args);
      this.off(event, onceWrapper);
    };
    return this.on(event, onceWrapper);
  }
}