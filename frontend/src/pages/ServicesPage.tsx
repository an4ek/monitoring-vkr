import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Card, Col, Descriptions, Row, Spin } from 'antd'
import { fetchIncidents } from '../api/incidents.ts'
import { useCatalog } from '../hooks/useCatalog.ts'
import { ServiceStatusTag } from '../components/StatusTags.tsx'
import { formatPercent } from '../utils/format.ts'
import { setServiceOwner } from '../api/catalog.ts'
import OwnerCell from '../components/OwnerCell.tsx'

// Сервисы: состояние каждого, доступность против цели (SLO) и открытые инциденты
export default function ServicesPage() {
  const catalog = useCatalog()
  const incidents = useQuery({ queryKey: ['incidents'], queryFn: fetchIncidents })

  if (catalog.isPending || incidents.isPending) {
    return <Spin />
  }

  return (
    <>
      <h1>Сервисы</h1>
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {catalog.services.map((service) => {
          const openIncidents = (incidents.data ?? []).filter(
            (item) => item.status !== 'resolved' && item.affected_service_ids.includes(service.id),
          )
          const resourceCount = catalog.resources.filter((item) => item.service_ids.includes(service.id)).length
          const belowTarget = service.availability < service.slo_target

          return (
            <Col key={service.id} xs={24} md={12} xl={8}>
              <Card title={service.name} extra={<ServiceStatusTag status={service.status} />}>
                <p className="hint" style={{ marginBottom: 12 }}>
                  {service.description}
                </p>
                <Descriptions
                  column={1}
                  size="small"
                  items={[
                    {
                      label: 'Доступность за 30 дней',
                      children: (
                        <span style={{ color: belowTarget ? '#c62828' : undefined }}>
                          {formatPercent(service.availability)} (цель {formatPercent(service.slo_target)})
                        </span>
                      ),
                    },
                    {
                      label: 'Ответственный',
                      children: (
                        <OwnerCell
                          ownerId={service.owner_id}
                          invalidate="services"
                          onAssign={(personId) => setServiceOwner(service.id, personId)}
                        />
                      ),
                    },
                    { label: 'Подразделение', children: catalog.departmentsById.get(service.department_id)?.name },
                    { label: 'Ресурсов', children: resourceCount },
                    {
                      label: 'Открытые инциденты',
                      children:
                        openIncidents.length === 0
                          ? 'нет'
                          : openIncidents.map((item) => (
                              <div key={item.id}>
                                <Link to={`/incidents/${item.id}`}>№{item.id}. {item.title}</Link>
                              </div>
                            )),
                    },
                  ]}
                />
              </Card>
            </Col>
          )
        })}
      </Row>
    </>
  )
}
