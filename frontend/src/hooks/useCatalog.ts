import { useQuery } from '@tanstack/react-query'
import { fetchDepartments, fetchPeople, fetchResources, fetchServices } from '../api/catalog.ts'

// Загружает весь каталог и превращает списки в словари «id → объект»,
// чтобы на страницах быстро находить имя ресурса, сервиса или сотрудника по id.
export function useCatalog() {
  // Состояние сервисов меняется при сбоях, поэтому сервисы перезапрашиваем каждые 5 секунд
  const services = useQuery({ queryKey: ['services'], queryFn: fetchServices, refetchInterval: 5_000 })
  const resources = useQuery({ queryKey: ['resources'], queryFn: fetchResources })
  const people = useQuery({ queryKey: ['people'], queryFn: fetchPeople })
  const departments = useQuery({ queryKey: ['departments'], queryFn: fetchDepartments })

  return {
    isPending: services.isPending || resources.isPending || people.isPending || departments.isPending,
    services: services.data ?? [],
    resources: resources.data ?? [],
    servicesById: new Map((services.data ?? []).map((item) => [item.id, item])),
    resourcesById: new Map((resources.data ?? []).map((item) => [item.id, item])),
    peopleById: new Map((people.data ?? []).map((item) => [item.id, item])),
    departmentsById: new Map((departments.data ?? []).map((item) => [item.id, item])),
  }
}
