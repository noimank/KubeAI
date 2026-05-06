type ModalApi = ReturnType<typeof import('antd/es/app').default.useApp>['modal']

let modalApi: ModalApi | null = null

export function setModalInstance(instance: ModalApi) {
  modalApi = instance
}

export function getModalInstance(): ModalApi | null {
  return modalApi
}
