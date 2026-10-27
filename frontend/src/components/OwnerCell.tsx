import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { App, Button, Select, Space } from 'antd'
import { useAuth } from '../hooks/useAuth.ts'
import { useCatalog } from '../hooks/useCatalog.ts'

type Props = {
  ownerId: number
  onAssign: (personId: number) => Promise<unknown>
  invalidate: string // какой список перезагрузить после назначения: 'resources' или 'services'
}

// Ответственный за ресурс или сервис. Руководитель видит кнопку «Назначить»
// и может выбрать другого сотрудника; остальные роли только смотрят.
export default function OwnerCell({ ownerId, onAssign, invalidate }: Props) {
  const { me } = useAuth()
  const catalog = useCatalog()
  const queryClient = useQueryClient()
  const { message } = App.useApp()
  const [editing, setEditing] = useState(false)

  const assign = useMutation({
    mutationFn: onAssign,
    onSuccess: () => {
      message.success('Ответственный назначен')
      setEditing(false)
      queryClient.invalidateQueries({ queryKey: [invalidate] })
    },
    onError: (error) => message.error(error.message),
  })

  const name = catalog.peopleById.get(ownerId)?.full_name ?? '—'
  if (me?.role !== 'manager') {
    return <>{name}</>
  }
  if (!editing) {
    return (
      <Space size={4}>
        {name}
        <Button size="small" type="link" onClick={() => setEditing(true)}>
          Назначить
        </Button>
      </Space>
    )
  }
  return (
    <Select<number>
      autoFocus
      defaultOpen
      size="small"
      style={{ width: 200 }}
      defaultValue={ownerId}
      loading={assign.isPending}
      onChange={(personId) => assign.mutate(personId)}
      onBlur={() => setEditing(false)}
      options={[...catalog.peopleById.values()].map((person) => ({ value: person.id, label: person.full_name }))}
    />
  )
}
