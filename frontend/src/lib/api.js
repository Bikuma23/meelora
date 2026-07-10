import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const api = {
  getConfig: () => axios.get(`${API}/config`).then((r) => r.data),
  getEmployees: () => axios.get(`${API}/employees`).then((r) => r.data),
  createEmployee: (data) => axios.post(`${API}/employees`, data).then((r) => r.data),
  updateEmployee: (id, data) => axios.put(`${API}/employees/${id}`, data).then((r) => r.data),
  deleteEmployee: (id) => axios.delete(`${API}/employees/${id}`).then((r) => r.data),
};
