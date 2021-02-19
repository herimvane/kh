package com.herim.kh.service.impl;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.herim.kh.dao.MyConfigRepository;
import com.herim.kh.domain.MyConfig;
import com.herim.kh.service.MyConfigService;

@Service
public class MyConfigServiceImpl implements MyConfigService {
	
	@Autowired
	private MyConfigRepository myConfigRepository;

	@Override
	public void save(MyConfig config) {
		myConfigRepository.save(config);
		
	}

	@Transactional
	@Override
	public void update(String key, String value) {
		myConfigRepository.updateValue(key, value);
		
	}

	@Override
	public List<MyConfig> getByKey(String key) {
		return myConfigRepository.findByKey(key);
	}

	

}
