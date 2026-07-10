import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const api = {
  listEmployees: (q) => axios.get(`${API}/employees`, { params: q ? { q } : {} }).then((r) => r.data),
  createEmployee: (d) => axios.post(`${API}/employees`, d).then((r) => r.data),
  updateEmployee: (id, d) => axios.put(`${API}/employees/${id}`, d).then((r) => r.data),
  deleteEmployee: (id) => axios.delete(`${API}/employees/${id}`).then((r) => r.data),
  getHypotheses: () => axios.get(`${API}/hypotheses`).then((r) => r.data),
  updateHypotheses: (d) => axios.put(`${API}/hypotheses`, d).then((r) => r.data),
  getBudget: (params) => axios.get(`${API}/budget`, { params }).then((r) => r.data),
  budgetPreview: (id, body) => axios.post(`${API}/employees/${id}/budget-preview`, body).then((r) => r.data),
  saveBudgetOverride: (id, body) => axios.put(`${API}/employees/${id}/budget-override`, body).then((r) => r.data),
};
