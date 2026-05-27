import { ref } from 'vue'

export const crudSyncTick = ref(0)

export function notifyCrudChanged () {
  crudSyncTick.value += 1
}
