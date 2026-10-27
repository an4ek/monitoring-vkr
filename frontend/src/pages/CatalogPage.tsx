import { useState } from 'react'
import { Input, Space, Table, Tag } from 'antd'
import type { TableProps } from 'antd'
import { useCatalog } from '../hooks/useCatalog.ts'
import { setResourceOwner } from '../api/catalog.ts'
import OwnerCell from '../components/OwnerCell.tsx'
import { environmentLabels, resourceTypeLabels } from '../utils/labels.ts'
import type { Environment, Resource, ResourceType } from '../types.ts'

// Каталог ресурсов: что есть в инфраструктуре, к каким сервисам относится,
// от чего зависит и кто отвечает. По этим связям система ищет первопричину сбоя.
export default function CatalogPage() {
  const [search, setSearch] = useState('')
  const catalog = useCatalog()

  const query = search.trim().toLowerCase()
  const rows = catalog.resources.filter(
    (item) =>
      query === '' ||
      item.name.toLowerCase().includes(query) ||
      item.description.toLowerCase().includes(query),
  )

  const columns: TableProps<Resource>['columns'] = [
    {
      title: 'Ресурс',
      dataIndex: 'name',
      render: (name: string, resource) => (
        <>
          <div style={{ fontWeight: 500 }}>{name}</div>
          <div className="hint">{resource.description}</div>
        </>
      ),
    },
    {
      title: 'Тип',
      dataIndex: 'type',
      render: (type: ResourceType) => resourceTypeLabels[type],
      filters: Object.entries(resourceTypeLabels).map(([value, text]) => ({ value, text })),
      onFilter: (value, resource) => resource.type === value,
    },
    {
      title: 'Окружение',
      dataIndex: 'environment',
      render: (env: Environment) => <Tag color={environmentLabels[env].color}>{environmentLabels[env].text}</Tag>,
      filters: [
        { value: 'prod', text: 'prod' },
        { value: 'test', text: 'test' },
      ],
      onFilter: (value, resource) => resource.environment === value,
    },
    {
      title: 'Сервисы',
      dataIndex: 'service_ids',
      render: (ids: number[]) => (
        <Space size={[0, 4]} wrap>
          {ids.map((id) => (
            <Tag key={id}>{catalog.servicesById.get(id)?.name}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: 'Зависит от',
      dataIndex: 'depends_on',
      render: (ids: number[]) =>
        ids.length === 0 ? '—' : ids.map((id) => catalog.resourcesById.get(id)?.name).join(', '),
    },
    {
      title: 'Ответственный',
      dataIndex: 'owner_id',
      render: (id: number, resource) => (
        <OwnerCell ownerId={id} invalidate="resources" onAssign={(personId) => setResourceOwner(resource.id, personId)} />
      ),
    },
  ]

  return (
    <>
      <h1>Каталог</h1>
      <Input.Search
        placeholder="Поиск по имени или описанию"
        allowClear
        style={{ maxWidth: 360, margin: '8px 0 16px' }}
        onChange={(event) => setSearch(event.target.value)}
      />
      <Table<Resource>
        rowKey="id"
        columns={columns}
        dataSource={rows}
        loading={catalog.isPending}
        pagination={false}
      />
    </>
  )
}
