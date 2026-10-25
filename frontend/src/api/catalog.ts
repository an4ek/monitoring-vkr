// Запросы данных каталога.
// Сейчас данные берутся из тестового файла (src/mocks/data.ts).
// Когда бэкенд будет готов, тело каждой функции заменим на apiGet('/services/') и т.п.,
// а страницы менять не придётся.
// import { departments, people, resources, services } from '../mocks/data.ts'
// import { fakeDelay } from './fake.ts'

// export const fetchServices = () => fakeDelay(services)
// export const fetchResources = () => fakeDelay(resources)
// export const fetchPeople = () => fakeDelay(people)
// export const fetchDepartments = () => fakeDelay(departments)


// Запросы данных каталога — теперь с реального бэкенда.
import { apiGet } from './client.ts'
import type { Department, Person, Resource, Service } from '../types.ts'

export const fetchServices = () => apiGet<Service[]>('/services/')
export const fetchResources = () => apiGet<Resource[]>('/resources/')
export const fetchPeople = () => apiGet<Person[]>('/people/')
export const fetchDepartments = () => apiGet<Department[]>('/departments/')