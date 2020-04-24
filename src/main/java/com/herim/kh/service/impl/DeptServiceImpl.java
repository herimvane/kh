package com.herim.kh.service.impl;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import com.herim.kh.dao.DeptRepository;
import com.herim.kh.domain.Dept;
import com.herim.kh.service.DeptService;

@Service
public class DeptServiceImpl implements DeptService {
	
	@Autowired
	private DeptRepository deptRepository;

	@Override
	public Dept saveDept(Dept dept) {
		return deptRepository.save(dept);
	}
	
	@Override
	public List<Dept> findAllDepts() {
		return deptRepository.findAll();
	}
}
