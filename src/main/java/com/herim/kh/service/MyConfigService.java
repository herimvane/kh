package com.herim.kh.service;

import java.util.List;

import com.herim.kh.domain.MyConfig;

public interface MyConfigService {
	
	void save(MyConfig config);
	void update(String key, String value);
	List<MyConfig> getByKey(String key);

}
